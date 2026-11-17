"""Job URL parsing and live-status verification (anti-ghost engine).

Statuses
  live        confirmed open via the employer's ATS portal API (Greenhouse / Lever)
  closed      portal or page says the posting is gone (404/410 or 'no longer available')
  unconfirmed page is reachable but cannot be confirmed open (generic site, Workday, etc.)
  error       could not check right now (network, 5xx, rate limit)"""
import html as htmllib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from . import urlsafe
from .htmltext import html_to_text

CLOSED_PHRASES = re.compile(
    r"no longer (accepting applications|available|open|accepting)|"
    r"(position|job|role|posting) (has been|is|was) (filled|closed|removed|cancel+ed)|"
    r"(job|posting|listing) (has )?expired|page not found|job not found|"
    r"this (job|position|posting) (is )?no longer", re.I)


@dataclass
class Portal:
    kind: str            # greenhouse | lever | workday | other
    company: str = ""
    job_id: str = ""
    api_url: str = ""


@dataclass
class Verification:
    url: str
    portal: str
    status: str
    reason: str
    title: str = ""
    company: str = ""
    location: str = ""
    jd_text: str = ""
    posted_age_days: int | None = None
    checked_at: str = ""
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _pretty(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def detect_portal(url: str) -> Portal:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    parts = [x for x in p.path.split("/") if x]
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        if len(parts) >= 3 and parts[1] == "jobs":
            tok, jid = parts[0], parts[2]
        elif parts and parts[0] == "embed":
            q = parse_qs(p.query)
            tok, jid = (q.get("for") or [""])[0], (q.get("token") or [""])[0]
        else:
            return Portal("other")
        if tok and jid.isdigit():
            return Portal("greenhouse", tok, jid,
                          f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs/{jid}")
    if host in ("jobs.lever.co", "jobs.eu.lever.co") and len(parts) >= 2:
        api = "api.eu.lever.co" if ".eu." in host else "api.lever.co"
        return Portal("lever", parts[0], parts[1], f"https://{api}/v0/postings/{parts[0]}/{parts[1]}")
    if host.endswith("myworkdayjobs.com"):
        return Portal("workday")
    return Portal("other")


def _age_days(dt: datetime | None, now: datetime) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def _greenhouse(data: dict, portal: Portal, now: datetime) -> dict:
    text, _ = html_to_text(htmllib.unescape(data.get("content") or ""))
    updated = None
    try:
        if data.get("updated_at"):
            updated = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
    except ValueError:
        pass
    return {"title": data.get("title", ""),
            "company": data.get("company_name") or _pretty(portal.company),
            "location": (data.get("location") or {}).get("name", ""),
            "jd_text": text, "age": _age_days(updated, now)}


def _lever(data: dict, portal: Portal, now: datetime) -> dict:
    parts = [data.get("descriptionPlain") or ""]
    for lst in data.get("lists") or []:
        body, _ = html_to_text(lst.get("content") or "")
        parts.append(f"{lst.get('text', '')}\n{body}")
    parts.append(data.get("additionalPlain") or "")
    created = None
    if isinstance(data.get("createdAt"), (int, float)):
        created = datetime.fromtimestamp(data["createdAt"] / 1000, tz=timezone.utc)
    cats = data.get("categories") or {}
    return {"title": data.get("text", ""), "company": _pretty(portal.company),
            "location": cats.get("location", ""),
            "jd_text": "\n\n".join(p for p in parts if p.strip()), "age": _age_days(created, now)}


def verify(url: str, client=None, resolver=None, now: datetime | None = None) -> Verification:
    """May raise urlsafe.UnsafeURL for blocked URLs."""
    now = now or datetime.now(timezone.utc)
    portal = detect_portal(url)
    stamp = now.isoformat(timespec="seconds")
    v = Verification(url=url, portal=portal.kind, status="error", reason="", checked_at=stamp)

    if portal.api_url:
        try:
            r = urlsafe.safe_get(portal.api_url, client, resolver, accept="application/json")
        except urlsafe.FetchError as e:
            v.reason = f"Portal API unreachable: {e}"
            return v
        if r.status in (404, 410):
            v.status, v.reason = "closed", f"{portal.kind} API reports the posting no longer exists"
            return v
        if r.status == 200:
            try:
                data = json.loads(r.text)
                if isinstance(data, dict) and data.get("ok") is False:
                    if "not found" in str(data.get("error", "")).lower():
                        v.status, v.reason = "closed", f"{portal.kind} API says the posting was not found"
                    else:
                        v.status, v.reason = "unconfirmed", f"{portal.kind} API returned an error body"
                    return v
                info = (_greenhouse if portal.kind == "greenhouse" else _lever)(data, portal, now)
            except (ValueError, AttributeError, TypeError):
                v.status, v.reason = "unconfirmed", "Portal API returned unreadable data"
                return v
            if not info["title"]:
                v.status, v.reason = "unconfirmed", "Portal API response had no job title; cannot confirm"
                return v
            v.status, v.reason = "live", f"Confirmed open via {portal.kind} API"
            v.title, v.company, v.location = info["title"], info["company"], info["location"]
            v.jd_text, v.posted_age_days = info["jd_text"], info["age"]
            return v
        v.reason = f"Portal API returned HTTP {r.status}; could not confirm"
        return v

    # Generic / Workday: page-level check only
    try:
        r = urlsafe.safe_get(url, client, resolver)
    except urlsafe.FetchError as e:
        v.reason = f"Page unreachable: {e}"
        return v
    if r.status in (404, 410):
        v.status, v.reason = "closed", f"Page returned HTTP {r.status}"
        return v
    if r.status != 200:
        v.reason = f"Page returned HTTP {r.status}; could not confirm"
        return v
    text, title = html_to_text(r.text)
    if CLOSED_PHRASES.search(text):
        v.status, v.reason = "closed", "Page text says the posting is closed or unavailable"
        v.title = title
        return v
    v.status = "unconfirmed"
    v.reason = ("Workday: only a page-level check is implemented; cannot confirm the posting is open"
                if portal.kind == "workday" else
                "Page is reachable, but this site has no supported portal API to confirm it is open")
    v.title, v.jd_text = title, text
    if len(text) < 300:
        v.warnings.append("Very little text extracted; the page may be JavaScript-rendered. "
                          "Paste the job description instead.")
    return v
