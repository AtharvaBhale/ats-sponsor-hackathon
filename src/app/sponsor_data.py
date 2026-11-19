"""Build data/processed/sponsors.db from USCIS Employer Data Hub CSVs and DOL LCA files.

Never guesses silently: column names are matched flexibly, but missing essentials raise an
error that lists the file's real headers, and every assumption is recorded in `warnings`."""
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .names import normalize_company
from .tabular import headers, iter_rows, norm_header

USCIS = {
    "fy": ["Fiscal Year"], "name": ["Employer", "Employer (Petitioner) Name", "Petitioner Name"],
    "ia": ["Initial Approval", "Initial Approvals"], "id": ["Initial Denial", "Initial Denials"],
    "ca": ["Continuing Approval", "Continuing Approvals"],
    "cd": ["Continuing Denial", "Continuing Denials"],
    "naics": ["NAICS", "Industry (NAICS) Code"], "state": ["State", "Petitioner State"],
}
LCA = {
    "name": ["EMPLOYER_NAME"], "status": ["CASE_STATUS"], "visa": ["VISA_CLASS"],
    "case": ["CASE_NUMBER"], "naics": ["NAICS_CODE"], "emp_state": ["EMPLOYER_STATE"],
    "ws_state": ["WORKSITE_STATE", "WORKSITE_STATE_1"], "secondary": ["SECONDARY_ENTITY"],
    "dependent": ["H-1B_DEPENDENT", "H1B_DEPENDENT"],
}
SCHEMA = """
CREATE TABLE employer (norm TEXT PRIMARY KEY, name TEXT, naics TEXT, state TEXT);
CREATE TABLE uscis (norm TEXT, fy INTEGER, ia INTEGER, id INTEGER, ca INTEGER, cd INTEGER,
                    PRIMARY KEY (norm, fy));
CREATE TABLE lca (norm TEXT, fy INTEGER, certified INTEGER, total INTEGER, sec_known INTEGER,
                  sec_yes INTEGER, mm_known INTEGER, mm_yes INTEGER, dependent INTEGER,
                  PRIMARY KEY (norm, fy));
CREATE TABLE alias (alias_norm TEXT PRIMARY KEY, norm TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


class DataError(Exception):
    pass


def _resolve(path, spec: dict, required: list) -> dict:
    by_norm = {norm_header(h): h for h in headers(path)}
    cols = {}
    for key, candidates in spec.items():
        for c in candidates:
            if norm_header(c) in by_norm:
                cols[key] = by_norm[norm_header(c)]
                break
    missing = [k for k in required if k not in cols]
    if missing:
        raise DataError(f"{Path(path).name}: could not find column(s) {missing}. "
                        f"Headers found: {sorted(by_norm.values())}")
    return cols


def _int(v) -> int:
    try:
        return int(float(str(v).replace(",", "").strip() or 0))
    except ValueError:
        return 0


def _year(v):
    m = re.search(r"(20\d\d|19\d\d)", str(v))
    return int(m.group(1)) if m else None


def build(db_path, uscis_files=(), lca_files=(), aliases=None) -> dict:
    """uscis_files: [(fy or None, path)], lca_files: [(fy, path)], aliases: {alias: canonical}."""
    warnings, emp = [], {}
    uscis = defaultdict(lambda: [0, 0, 0, 0])
    lca = defaultdict(lambda: defaultdict(int))
    lca_naics = defaultdict(Counter)
    stats = {"uscis_rows": 0, "lca_rows": 0, "lca_kept": 0, "lca_duplicates": 0}

    def note(norm, name, naics="", state=""):
        e = emp.setdefault(norm, {"name": name, "naics": Counter(), "state": Counter()})
        if naics:
            e["naics"][naics] += 1
        if state:
            e["state"][state] += 1

    for fy_arg, path in uscis_files:
        c = _resolve(path, USCIS, ["name", "ia", "ca"] + ([] if fy_arg else ["fy"]))
        for k in ("id", "cd"):
            if k not in c:
                warnings.append(f"{Path(path).name}: no denial column '{k}'; approval rate unavailable")
        keep = {norm_header(v) for v in c.values()}
        for row in iter_rows(path, keep):
            fy = fy_arg or _year(row.get(c["fy"]))
            norm = normalize_company(row.get(c["name"], ""))
            if not fy or not norm:
                continue
            stats["uscis_rows"] += 1
            a = uscis[(norm, fy)]
            for i, k in enumerate(("ia", "id", "ca", "cd")):
                a[i] += _int(row.get(c.get(k), 0)) if k in c else 0
            note(norm, row[c["name"]], row.get(c.get("naics", ""), ""), row.get(c.get("state", ""), ""))

    for fy, path in lca_files:
        c = _resolve(path, LCA, ["name"])
        for k, msg in (("status", "no CASE_STATUS: counting every row as certified"),
                       ("visa", "no VISA_CLASS: not filtering to H-1B"),
                       ("case", "no CASE_NUMBER: cannot de-duplicate")):
            if k not in c:
                warnings.append(f"{Path(path).name}: {msg}")
        keep = {norm_header(v) for v in c.values()}
        seen = set()
        for row in iter_rows(path, keep):
            stats["lca_rows"] += 1
            if "visa" in c and row.get(c["visa"], "").strip().upper() != "H-1B":
                continue
            if "case" in c:
                cn = row.get(c["case"], "")
                if cn in seen:
                    stats["lca_duplicates"] += 1
                    continue
                seen.add(cn)
            norm = normalize_company(row.get(c["name"], ""))
            if not norm:
                continue
            stats["lca_kept"] += 1
            a = lca[(norm, fy)]
            a["total"] += 1
            a["certified"] += (row.get(c["status"], "").lower() == "certified") if "status" in c else 1
            sec = row.get(c.get("secondary", ""), "")
            if sec:
                a["sec_known"] += 1
                a["sec_yes"] += sec.upper().startswith("Y")
            es, ws = row.get(c.get("emp_state", ""), ""), row.get(c.get("ws_state", ""), "")
            if es and ws:
                a["mm_known"] += 1
                a["mm_yes"] += es.upper() != ws.upper()
            a["dependent"] += row.get(c.get("dependent", ""), "").upper().startswith("Y")
            nc = row.get(c.get("naics", ""), "")
            if nc:
                lca_naics[norm][nc] += 1
            note(norm, row[c["name"]], "", row.get(c.get("emp_state", ""), ""))

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(db_path)
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO employer VALUES (?,?,?,?)", [
        (n, e["name"], (lca_naics[n].most_common(1) or e["naics"].most_common(1) or [("", 0)])[0][0],
         (e["state"].most_common(1) or [("", 0)])[0][0]) for n, e in emp.items()])
    db.executemany("INSERT INTO uscis VALUES (?,?,?,?,?,?)",
                   [(n, fy, *v) for (n, fy), v in uscis.items()])
    db.executemany("INSERT INTO lca VALUES (?,?,?,?,?,?,?,?,?)", [
        (n, fy, a["certified"], a["total"], a["sec_known"], a["sec_yes"], a["mm_known"],
         a["mm_yes"], a["dependent"]) for (n, fy), a in lca.items()])
    for alias, canon in (aliases or {}).items():
        db.execute("INSERT OR REPLACE INTO alias VALUES (?,?)",
                   (normalize_company(alias), normalize_company(canon)))
    meta = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "uscis_fys": ",".join(str(y) for y in sorted({k[1] for k in uscis})),
            "lca_fys": ",".join(str(y) for y in sorted({k[1] for k in lca})),
            "employers": str(len(emp))}
    db.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    db.commit()
    db.close()
    return {**stats, **meta, "warnings": warnings}
