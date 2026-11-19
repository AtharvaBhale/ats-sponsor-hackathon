"""Sponsorship tiers: Proven Sponsor / Emerging Sponsor / OPT-Only / Non-Sponsor (+ Unknown).

Rules (thresholds live in TierConfig; USCIS window = latest 4 fiscal years in the data):
  Proven   : approvals in >= 3 of the window's years AND >= 10 initial approvals AND approval
             rate >= 90% AND (if LCA data is loaded) certified LCAs in the last 2 LCA years.
  Emerging : some H-1B evidence in the window but not Proven (few years/volume, low approval
             rate, no recent LCAs, or LCA filings only because no USCIS data is loaded).
  OPT-Only : no H-1B evidence, but the posting mentions OPT/CPT/F-1 or the company is on the
             user-curated OPT list.
  Non-Sponsor : no H-1B evidence found. Confidence is LOW when the name matched nothing.
A posting that says it does not sponsor overrides per-role via `effective_tier`."""
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .names import normalize_company
from .staffing import LcaStats

PROVEN, EMERGING, OPT_ONLY, NON, UNKNOWN = (
    "Proven Sponsor", "Emerging Sponsor", "OPT-Only", "Non-Sponsor", "Unknown")
DISCLAIMER = ("Based on public USCIS/DOL records matched by company name. Subsidiaries and "
              "renamed entities can be missed. Informational only, not legal advice.")


@dataclass
class TierConfig:
    window_years: int = 4
    proven_min_years: int = 3
    proven_min_initial: int = 10
    proven_min_rate: float = 0.90
    lca_recent_years: int = 2


_NO = [re.compile(p, re.I) for p in (
    r"\b(?:will not|won'?t|cannot|can'?t|unable to|not able to|does not|do not|not in a position to)"
    r"\s+(?:\w+\s+){0,3}?sponsor",
    r"\bno (?:visa |h-?1b )?sponsorship\b",
    r"\bwithout (?:the need for |requiring |needing |now or in the future )?(?:\w+\s+){0,3}?sponsorship\b",
    r"\bsponsorship (?:is )?(?:not|unavailable)\b",
    r"\bnot (?:require|requiring|need)\s+(?:\w+\s+){0,2}sponsorship",
)]
_OFFERS = [re.compile(p, re.I) for p in (
    r"\b(?:will|can|able to|happy to|we)\s+(?:\w+\s+){0,2}?(?:sponsor|provide (?:visa )?sponsorship|support (?:h-?1b|visa))",
    r"\b(?:visa )?sponsorship (?:is |may be )?(?:available|provided|offered)\b",
    r"\bh-?1b (?:transfer|sponsorship) (?:is )?(?:available|supported|offered)\b",
)]
_OPT_PATTERNS = [re.compile(r"\bSTEM[- ]OPT\b", re.I), re.compile(r"\bOPT\b"), re.compile(r"\bCPT\b"),
        re.compile(r"\bF-?1\b")]


def posting_signal(text: str) -> str:
    """'no_sponsorship' | 'offers' | 'opt_ok' | 'unknown'. Explicit refusals win."""
    if any(p.search(text or "") for p in _NO):
        return "no_sponsorship"
    if any(p.search(text or "") for p in _OFFERS):
        return "offers"
    if any(p.search(text or "") for p in _OPT_PATTERNS):
        return "opt_ok"
    return "unknown"


@dataclass
class Profile:
    name: str
    norm: str
    naics: str
    state: str
    match_type: str                       # exact | alias
    uscis: dict = field(default_factory=dict)   # fy -> {ia,id,ca,cd}
    lca: dict = field(default_factory=dict)     # fy -> {certified,total,...}
    latest_uscis_fy: int | None = None
    latest_lca_fy: int | None = None

    def lca_stats(self) -> LcaStats | None:
        if not self.lca:
            return None
        g = lambda k: sum(d[k] for d in self.lca.values())
        n = g("total")
        return LcaStats(
            n=n, secondary_ratio=g("sec_yes") / g("sec_known") if g("sec_known") else None,
            mismatch_ratio=g("mm_yes") / g("mm_known") if g("mm_known") else None,
            h1b_dependent=g("dependent") > n / 2, naics=self.naics or None)


class SponsorDB:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.meta = {r["key"]: r["value"] for r in self.db.execute("SELECT * FROM meta")}
        self.latest_uscis = self._max("uscis")
        self.latest_lca = self._max("lca")

    def _max(self, table):
        return self.db.execute(f"SELECT MAX(fy) FROM {table}").fetchone()[0]

    def related(self, norm: str, limit: int = 5) -> list:
        if not norm:
            return []
        with self.lock:
            rows = self.db.execute("SELECT name FROM employer WHERE norm LIKE ? LIMIT ?",
                                   (norm + " %", limit)).fetchall()
        return [r["name"] for r in rows]

    def profile(self, company: str) -> Profile | None:
        norm = normalize_company(company)
        if not norm:
            return None
        with self.lock:
            match_type = "exact"
            row = self.db.execute("SELECT * FROM employer WHERE norm=?", (norm,)).fetchone()
            if row is None:
                a = self.db.execute("SELECT norm FROM alias WHERE alias_norm=?", (norm,)).fetchone()
                row = a and self.db.execute("SELECT * FROM employer WHERE norm=?", (a["norm"],)).fetchone()
                match_type = "alias"
            if row is None:
                return None
            n = row["norm"]
            uscis = {r["fy"]: {"ia": r["ia"], "id": r["id"], "ca": r["ca"], "cd": r["cd"]}
                     for r in self.db.execute("SELECT * FROM uscis WHERE norm=?", (n,))}
            lca = {r["fy"]: dict(r) for r in self.db.execute("SELECT * FROM lca WHERE norm=?", (n,))}
        return Profile(row["name"], n, row["naics"] or "", row["state"] or "", match_type,
                       uscis, lca, self.latest_uscis, self.latest_lca)


def classify(db: SponsorDB | None, company: str, posting_text: str = "",
             opt_list: set | None = None, cfg: TierConfig = TierConfig()) -> dict:
    if db is None:
        return {"tier": UNKNOWN, "effective_tier": UNKNOWN, "confidence": "none",
                "reasons": ["Sponsor database not loaded (run scripts/build_sponsor_data.py)"],
                "role_note": None, "related_entities": [], "disclaimer": DISCLAIMER}
    prof = db.profile(company)
    signal = posting_signal(posting_text)
    norm = normalize_company(company)
    reasons, evidence = [], {}
    related = db.related(norm) if prof is None else []

    u_by_fy = {}
    if prof and prof.latest_uscis_fy:
        lo = prof.latest_uscis_fy - cfg.window_years + 1
        u_by_fy = {fy: d for fy, d in prof.uscis.items() if lo <= fy <= prof.latest_uscis_fy}
    years_active = sum(1 for d in u_by_fy.values() if d["ia"] + d["ca"] > 0)
    ia_total = sum(d["ia"] for d in u_by_fy.values())
    approvals = sum(d["ia"] + d["ca"] for d in u_by_fy.values())
    denials = sum(d["id"] + d["cd"] for d in u_by_fy.values())
    rate = approvals / (approvals + denials) if approvals + denials else None
    uscis_loaded = db.latest_uscis is not None

    lca_loaded = db.latest_lca is not None
    lca_recent = 0
    if prof and prof.latest_lca_fy:
        lo = prof.latest_lca_fy - cfg.lca_recent_years + 1
        lca_recent = sum(d["certified"] for fy, d in prof.lca.items() if lo <= fy <= prof.latest_lca_fy)

    evidence = {"uscis_years_active": years_active, "initial_approvals": ia_total,
                "approval_rate": round(rate, 3) if rate is not None else None,
                "certified_lca_recent": lca_recent,
                "uscis_window": sorted(u_by_fy) or None}

    has_h1b = years_active >= 1 or lca_recent >= 1
    recently_active = (not lca_loaded) or lca_recent > 0
    proven = (uscis_loaded and years_active >= cfg.proven_min_years and ia_total >= cfg.proven_min_initial
              and (rate is None or rate >= cfg.proven_min_rate) and recently_active)

    if proven:
        tier, conf = PROVEN, "high"
        reasons.append(f"Approvals in {years_active} of the last {cfg.window_years} fiscal years, "
                       f"{ia_total} initial approvals, {rate:.0%} approval rate"
                       if rate is not None else f"Approvals in {years_active} years, {ia_total} initial")
        if lca_loaded:
            reasons.append(f"{lca_recent} certified LCAs in the last {cfg.lca_recent_years} fiscal years")
    elif has_h1b:
        tier = EMERGING
        conf = "high" if uscis_loaded else "medium"
        if not uscis_loaded:
            reasons.append("LCA filings found, but no USCIS approval data is loaded (intent, not approvals)")
        else:
            reasons.append(f"H-1B activity in {years_active} year(s) with {ia_total} initial approvals")
            if years_active >= cfg.proven_min_years and ia_total >= cfg.proven_min_initial:
                if rate is not None and rate < cfg.proven_min_rate:
                    reasons.append(f"Approval rate {rate:.0%} is below the {cfg.proven_min_rate:.0%} Proven bar")
                if not recently_active:
                    reasons.append(f"No certified LCAs in the last {cfg.lca_recent_years} fiscal years")
            else:
                reasons.append("Below the Proven thresholds on years or volume")
        if lca_recent and uscis_loaded:
            reasons.append(f"{lca_recent} certified LCAs recently")
    elif prof is None and related:
        tier, conf = UNKNOWN, "low"
        reasons.append("No exact match, but similar filer names exist (" + "; ".join(related[:3])
                       + "). Add an alias in data/aliases.json if one is the same company.")
    elif signal == "opt_ok" or (opt_list and norm in opt_list):
        tier, conf = OPT_ONLY, "medium"
        reasons.append("No H-1B filings found; " + ("posting mentions OPT/CPT/F-1"
                       if signal == "opt_ok" else "company is on the OPT-friendly list"))
    else:
        tier = NON
        if prof:
            last = max((fy for fy, d in prof.uscis.items() if d["ia"] + d["ca"] > 0), default=None)
            conf = "medium"
            reasons.append("No H-1B approvals in the recent window"
                           + (f" (last approvals in FY{last})" if last else ""))
        else:
            conf = "low"
            reasons.append("No filings found under this company name; subsidiaries or a different "
                           "legal name may exist")

    role_note, effective = None, tier
    if signal == "no_sponsorship":
        role_note, effective = "This posting says it does not offer sponsorship.", f"{NON} (this role)"
    elif signal == "offers" and tier in (NON, OPT_ONLY):
        role_note = "Posting says sponsorship is offered, but no filing history was found; verify."
    elif signal == "offers":
        role_note = "Posting says sponsorship is offered."

    return {"tier": tier, "effective_tier": effective, "confidence": conf, "reasons": reasons,
            "evidence": evidence, "role_note": role_note, "match": prof.match_type if prof else "none",
            "matched_name": prof.name if prof else None,
            "related_entities": related,
            "data": {"uscis_fys": db.meta.get("uscis_fys"), "lca_fys": db.meta.get("lca_fys")},
            "disclaimer": DISCLAIMER}


# ---- module-level handle so routes and tests can swap the database
_DB: SponsorDB | None = None
_OPT_LIST: set | None = None


def get_db() -> SponsorDB | None:
    global _DB
    if _DB is None:
        p = Path(os.getenv("SPONSOR_DB", "data/processed/sponsors.db"))
        if p.exists():
            _DB = SponsorDB(p)
    return _DB


def set_db(db: SponsorDB | None) -> None:
    global _DB
    _DB = db


def get_opt_list() -> set:
    global _OPT_LIST
    if _OPT_LIST is None:
        p = Path(os.getenv("OPT_LIST", "data/opt_friendly.txt"))
        _OPT_LIST = {normalize_company(x) for x in p.read_text().splitlines() if x.strip()} if p.exists() else set()
    return _OPT_LIST


def tier_for(company: str, posting_text: str = "") -> dict:
    return classify(get_db(), company, posting_text, get_opt_list())
