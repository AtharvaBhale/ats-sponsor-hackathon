"""SQLite job store with 24-hour stale/closed purge and a background re-verifier."""
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from . import urlsafe

SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (
  url TEXT PRIMARY KEY, portal TEXT, status TEXT, reason TEXT, title TEXT, company TEXT,
  location TEXT, jd_text TEXT, first_seen TEXT, last_checked TEXT, last_ok TEXT,
  fail_count INTEGER DEFAULT 0)"""
OK_STATUSES = ("live", "unconfirmed")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class JobStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.execute(SCHEMA)
            self.db.commit()

    def save(self, v, now: datetime | None = None) -> None:
        now_s = _iso(now or datetime.now(timezone.utc))
        with self.lock:
            old = self.db.execute("SELECT * FROM jobs WHERE url=?", (v.url,)).fetchone()
            ok = v.status in OK_STATUSES
            last_ok = now_s if ok else (old["last_ok"] if old else None)
            fails = 0 if v.status != "error" else (old["fail_count"] + 1 if old else 1)
            keep = lambda new, col: new or (old[col] if old else "")  # keep old text on error
            self.db.execute(
                """INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET portal=excluded.portal, status=excluded.status,
                   reason=excluded.reason, title=excluded.title, company=excluded.company,
                   location=excluded.location, jd_text=excluded.jd_text,
                   last_checked=excluded.last_checked, last_ok=excluded.last_ok,
                   fail_count=excluded.fail_count""",
                (v.url, v.portal, v.status, v.reason, keep(v.title, "title"),
                 keep(v.company, "company"), keep(v.location, "location"),
                 keep(v.jd_text, "jd_text"), old["first_seen"] if old else now_s,
                 now_s, last_ok, fails))
            self.db.commit()

    def list(self, live_only: bool = False) -> list:
        q = "SELECT * FROM jobs" + (" WHERE status='live'" if live_only else "")
        with self.lock:
            return [dict(r) for r in self.db.execute(q + " ORDER BY last_checked DESC")]

    def purge(self, now: datetime | None = None, max_age_hours: int = 24) -> list:
        """Remove closed postings and any posting not confirmed reachable for max_age_hours."""
        now = now or datetime.now(timezone.utc)
        cutoff = _iso(now - timedelta(hours=max_age_hours))
        with self.lock:
            rows = self.db.execute(
                "SELECT url FROM jobs WHERE status='closed' OR COALESCE(last_ok, first_seen) < ?",
                (cutoff,)).fetchall()
            urls = [r["url"] for r in rows]
            self.db.executemany("DELETE FROM jobs WHERE url=?", [(u,) for u in urls])
            self.db.commit()
        return urls

    def reverify_all(self, verify_fn, now: datetime | None = None) -> dict:
        """verify_fn(url) -> Verification. Re-checks every stored job, then purges."""
        now = now or datetime.now(timezone.utc)
        counts = {"checked": 0, "live": 0, "unconfirmed": 0, "closed": 0, "error": 0}
        for row in self.list():
            try:
                v = verify_fn(row["url"])
            except (urlsafe.UnsafeURL, urlsafe.FetchError):
                continue
            self.save(v, now)
            counts["checked"] += 1
            counts[v.status] += 1
        counts["purged"] = self.purge(now)
        return counts


def start_background(get_store, make_client, verify_fn, interval_s: int = 3600):
    """Daemon thread: re-verify and purge on an interval. Returns a stop Event."""
    stop = threading.Event()

    def loop():
        while not stop.wait(interval_s):
            client = make_client()
            try:
                get_store().reverify_all(lambda u: verify_fn(u, client))
            except Exception:
                pass  # never let the scheduler die
            finally:
                client.close()

    threading.Thread(target=loop, daemon=True, name="job-reverifier").start()
    return stop
