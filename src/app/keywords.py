"""Domain-independent keyword fit between a job description and a resume.

The skill vocabulary in skills.py only knows tech terms. This module works for any field by
comparing the job's most frequent meaningful words (plus known skills) with the resume's."""
import re
from collections import Counter

from .skills import extract_skills

STOP = set("""
about above across after again against also another around because before being below between both
bring build candidate candidates company could daily deliver does doing during each either else
employer employees ensure especially every experience experienced following from further great have
having help helping here highly including into join joining just keep known like looking make
making many more most much must need needs next only open opportunity other others over part
people please position preferred prior provide qualifications qualified required requirements
requires responsibilities responsible role roles same should since skills some strong such than
that their them then there these they this those through together towards under until upon using
very want ways well were what when where whether which while will with within without work working
works would year years your yours ability abilities able apply applicants application benefits
based days degree environment equal etc excellent full good ideal level local location new offer
offers plus related remote salary seeking small successful summer team teams time type
""".split())
_WORD = re.compile(r"[a-z][a-z0-9+#]*(?:[.-][a-z0-9+#]+)*")


def stem(w: str) -> str:
    for suf in ("ingly", "edly", "ing", "ies", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def _words(text: str):
    return [w for w in _WORD.findall(text.lower()) if len(w) >= 4 and w not in STOP]


def term_set(text: str) -> set:
    return {stem(w) for w in _words(text)} | extract_skills(text)


def fit(jd: str, evidence: str, top: int = 40) -> dict:
    """How many of the job's key terms already appear in the candidate's evidence."""
    counts, shown = Counter(), {}
    for w in _words(jd):
        s = stem(w)
        counts[s] += 1
        shown.setdefault(s, w)
    skills = extract_skills(jd)
    for sk in skills:
        counts[sk] += 2
        shown.setdefault(sk, sk)
    ranked = [s for s, _ in counts.most_common(top)]
    ranked += [s for s in skills if s not in ranked]
    if not ranked:
        return {"score": None, "level": None, "matched": [], "missing": [], "matched_stems": []}
    have = term_set(evidence)
    matched = [s for s in ranked if s in have]
    missing = [s for s in ranked if s not in have]
    score = len(matched) / len(ranked)
    return {"score": round(score, 2),
            "level": "strong" if score >= 0.5 else "partial" if score >= 0.25 else "weak",
            "matched": [shown[s] for s in matched][:15], "missing": [shown[s] for s in missing][:12],
            "matched_stems": matched}


def gained(original: str, rewritten: str, allowed_stems: set) -> list:
    """Job keywords the candidate can truthfully claim that the rewrite adds to the bullet."""
    return sorted((term_set(rewritten) - term_set(original)) & allowed_stems)
