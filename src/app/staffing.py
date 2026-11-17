"""Staffing / recruiting / body-shop detection. Deterministic, explainable, advisory.

Every point of score is tied to a human-readable reason that the UI can show.
This is a heuristic over public signals, NOT a factual claim about a company."""
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .names import normalize_company

MIN_LCA = 20  # ignore LCA ratios below this volume: too noisy

STRONG_NAME = re.compile(
    r"\b(staffing|recruit\w*|personnel|manpower|placement|headhunt\w*|executive search)\b")
MEDIUM_NAME = re.compile(r"\b(talent|workforce|human capital|employment services)\b")
WEAK_NAME = re.compile(r"\b(consulting|consultants|consultancy|infotech|it services|"
                       r"information technology|solutions)\b")
IT_NAICS = {"541511", "541512", "541513", "541519"}

_CONTRACT = [
    (r"\bw-?2 only\b", "W2 only"), (r"\bw-?2 contract\b", "W2 contract"),
    (r"\bc2c\b|\bcorp[- ]to[- ]corp\b", "C2C"), (r"\b1099\b", "1099"),
    (r"\bcontract[- ]to[- ]hire\b", "contract-to-hire"),
    (r"\b\d+[- ]month contract\b|\bcontract (position|role)\b", "fixed contract"),
    (r"\bon bench\b", "bench"), (r"\b(our|direct|end) client\b|\bclient of ours\b", "client placement"),
    (r"\bh-?1b transfer\b", "H-1B transfer wording"), (r"\bopt ?/ ?cpt\b", "OPT/CPT wording"),
    (r"\bgc ?ead\b", "GC/EAD wording"),
]
_CONTRACT = [(re.compile(p, re.I), label) for p, label in _CONTRACT]
_DIRECT = re.compile(
    r"\b(direct hire|permanent (employee|position|role)|full[- ]time (permanent|employee))\b", re.I)


@dataclass
class LcaStats:
    n: int = 0
    secondary_ratio: float | None = None   # share of LCAs naming a secondary (client) entity
    mismatch_ratio: float | None = None    # share with worksite state != employer state
    h1b_dependent: bool = False
    naics: str | None = None


@dataclass
class StaffingAssessment:
    name: str
    level: str                      # likely | possible | unlikely
    score: int
    reasons: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    employment_model: str = "unknown"   # direct_hire | contract_only | mixed | unknown
    contract_signals: list = field(default_factory=list)

    def badge(self) -> dict | None:
        if self.level == "unlikely":
            return None
        label = "Likely" if self.level == "likely" else "Possible"
        return {
            "title": f"{label} staffing intermediary",
            "risks": [
                "H-1B transfers: sponsorship may depend on the agency's client contracts, and a "
                "change of worksite can require new filings.",
                "Bench periods: pay and hours may be unstable between client assignments. Ask how "
                "unassigned time is handled.",
                "Client-site dependency: your day-to-day work location and manager may belong to a "
                "client, and the assignment can end when the client contract does.",
            ],
            "ask": "Ask: is this W-2 permanent employment or contract? Who is the end client?",
            "disclaimer": "Automated heuristic from public signals; it can be wrong. "
                          "Informational only, not legal advice.",
        }

    def to_dict(self) -> dict:
        return {"name": self.name, "level": self.level, "score": self.score,
                "reasons": self.reasons, "notes": self.notes,
                "employment_model": self.employment_model,
                "contract_signals": self.contract_signals, "badge": self.badge()}


def classify_posting(text: str) -> tuple[str, list]:
    labels = sorted({label for pat, label in _CONTRACT if pat.search(text)})
    if labels:
        return "contract", labels
    if _DIRECT.search(text):
        return "direct", []
    return "unknown", []


def assess(name: str, naics: str | None = None, lca: LcaStats | None = None,
           postings: list | None = None, overrides: dict | None = None) -> StaffingAssessment:
    norm = normalize_company(name)
    score, reasons, notes = 0, [], []

    # 1. Name
    if STRONG_NAME.search(norm):
        score += 40; reasons.append("Company name contains a staffing/recruiting term (+40)")
    elif MEDIUM_NAME.search(norm):
        score += 20; reasons.append("Company name contains a talent/workforce term (+20)")
    elif WEAK_NAME.search(norm):
        score += 10; reasons.append("Company name suggests consulting/IT services (+10)")

    # 2. NAICS
    code = str(naics or (lca.naics if lca else "") or "")
    if code.startswith("5613"):
        score += 45; reasons.append(f"NAICS {code} is employment services (+45)")
    elif code in IT_NAICS:
        score += 10; reasons.append(f"NAICS {code} is IT services; common for consultancies (+10)")

    # 3. DOL LCA patterns
    if lca is not None:
        if lca.n < MIN_LCA:
            notes.append(f"LCA signals ignored: only {lca.n} filings (need {MIN_LCA}+)")
        else:
            r = lca.secondary_ratio
            if r is not None:
                pts = 35 if r >= 0.5 else 20 if r >= 0.25 else 10 if r >= 0.10 else 0
                if pts:
                    score += pts
                    reasons.append(f"{r:.0%} of LCAs name a secondary/client entity (+{pts})")
            if lca.mismatch_ratio is not None and lca.mismatch_ratio >= 0.8:
                score += 15
                reasons.append(f"{lca.mismatch_ratio:.0%} of worksites are outside the employer's "
                               "state (+15)")
            if lca.h1b_dependent:
                score += 10; reasons.append("Flagged H-1B dependent employer (+10)")

    # 4. Posting language + employment model
    contract_n = direct_n = 0
    signals: set = set()
    for p in postings or []:
        kind, labels = classify_posting(p)
        contract_n += kind == "contract"
        direct_n += kind == "direct"
        signals.update(labels)
    if signals:
        pts = min(30, 10 * len(signals))
        score += pts
        reasons.append(f"Posting language: {', '.join(sorted(signals))} (+{pts})")
    if contract_n and not direct_n:
        model = "contract_only"
    elif direct_n and not contract_n:
        model = "direct_hire"
    elif contract_n and direct_n:
        model = "mixed"
    else:
        model = "unknown"

    score = min(score, 100)
    level = "likely" if score >= 60 else "possible" if score >= 30 else "unlikely"

    ov = (overrides or {}).get(norm)
    if ov in {"likely", "possible", "unlikely"}:
        level = ov
        reasons.append(f"Manual override: {ov}")

    return StaffingAssessment(name, level, score, reasons, notes, model, sorted(signals))


def filter_companies(items: list, hide_staffing: bool = False, direct_hire_only: bool = False,
                     strict: bool = False) -> list:
    """items: list of dicts with an 'assessment' (StaffingAssessment).
    hide_staffing: drop 'likely' (and 'possible' when strict).
    direct_hire_only: drop contract-only companies, and likely staffing firms with no
    direct-hire evidence."""
    out = []
    for it in items:
        a = it["assessment"]
        if hide_staffing and (a.level == "likely" or (strict and a.level == "possible")):
            continue
        if direct_hire_only and (a.employment_model == "contract_only" or
                                 (a.level == "likely" and a.employment_model != "direct_hire")):
            continue
        out.append(it)
    return out


# ---- DOL LCA aggregation (pure function over dict rows; verify column names per fiscal year)
_COLS = {
    "employer": ["EMPLOYER_NAME"], "emp_state": ["EMPLOYER_STATE"],
    "ws_state": ["WORKSITE_STATE", "WORKSITE_STATE_1"],
    "secondary": ["SECONDARY_ENTITY"], "dependent": ["H-1B_DEPENDENT", "H1B_DEPENDENT"],
    "naics": ["NAICS_CODE"],
}


def _get(row: dict, key: str) -> str:
    for c in _COLS[key]:
        v = row.get(c)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def aggregate_lca(rows) -> dict:
    acc = defaultdict(lambda: {"n": 0, "sec_known": 0, "sec_yes": 0, "mm_known": 0,
                               "mm_yes": 0, "dep": 0, "naics": {}})
    for row in rows:
        name = normalize_company(_get(row, "employer"))
        if not name:
            continue
        a = acc[name]
        a["n"] += 1
        sec = _get(row, "secondary")
        if sec:
            a["sec_known"] += 1; a["sec_yes"] += sec.upper().startswith("Y")
        es, ws = _get(row, "emp_state"), _get(row, "ws_state")
        if es and ws:
            a["mm_known"] += 1; a["mm_yes"] += es.upper() != ws.upper()
        a["dep"] += _get(row, "dependent").upper().startswith("Y")
        nc = _get(row, "naics")
        if nc:
            a["naics"][nc] = a["naics"].get(nc, 0) + 1
    result = {}
    for name, a in acc.items():
        top = max(a["naics"], key=a["naics"].get) if a["naics"] else None
        result[name] = LcaStats(
            n=a["n"],
            secondary_ratio=a["sec_yes"] / a["sec_known"] if a["sec_known"] else None,
            mismatch_ratio=a["mm_yes"] / a["mm_known"] if a["mm_known"] else None,
            h1b_dependent=a["dep"] > a["n"] / 2, naics=top)
    return result
