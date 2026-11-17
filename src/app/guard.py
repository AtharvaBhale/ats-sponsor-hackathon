"""Anti-fabrication guard. Deterministic: a rewrite may only contain claims that the
evidence (original resume + user-confirmed additions + parsed uploads) already contains."""
import re
from dataclasses import dataclass, field

from .skills import extract_skills

_NUM = re.compile(r"\d[\d,]*\.?\d*")
_DEGREE = re.compile(
    r"\b(Ph\.?D\.?|M\.?Sc?\.?|B\.?Sc?\.?|MBA|Bachelor'?s?|Master'?s?|Doctorate)\b")
_CERT = re.compile(r"\b(certified|certification|certificate)\b", re.I)
_PROPER = re.compile(r"\b[A-Z][A-Za-z0-9&+#]*")
_STOP = {"I", "A", "The", "And", "In", "On", "To", "Of", "For", "With", "By", "At"}


@dataclass
class GuardResult:
    ok: bool
    violations: list = field(default_factory=list)


def _nums(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUM.findall(text)}


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9&+#]+", text)}


def check(rewritten: str, evidence: str) -> GuardResult:
    v = []
    ev_low = evidence.lower()

    for n in _nums(rewritten) - _nums(evidence):
        v.append(f"new number not in evidence: {n}")

    for s in extract_skills(rewritten) - extract_skills(evidence):
        v.append(f"new skill/tool not in evidence: {s}")

    for m in _DEGREE.finditer(rewritten):
        if m.group(0).lower() not in ev_low:
            v.append(f"degree not in evidence: {m.group(0)}")

    if _CERT.search(rewritten) and not _CERT.search(evidence):
        v.append("certification claim not in evidence")

    ev_words = _words(evidence)
    for i, m in enumerate(_PROPER.finditer(rewritten)):
        tok = m.group(0)
        if i == 0 or tok in _STOP:  # sentence-initial verb or stopword
            continue
        if tok.lower() not in ev_words:
            v.append(f"new proper noun not in evidence: {tok}")

    return GuardResult(ok=not v, violations=sorted(set(v)))
