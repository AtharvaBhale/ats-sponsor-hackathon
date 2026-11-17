"""Deterministic skill/keyword extraction. No LLM: fast, testable, explainable.

Ordinary terms match case-insensitively on word boundaries. Ambiguous terms that are also
common English words (go, r, rest, excel, spark, spring, react, node, ML) use stricter,
mostly case-sensitive patterns so prose like "go-to-market" or "excel at" never matches.
Trade-off: these are detected with lower recall (e.g. a bare "experience with Go." is missed);
the guard's proper-noun check backstops that for rewrites."""
import re

# canonical name -> aliases (unambiguous terms only)
VOCAB = {
    "python": [], "java": [], "javascript": ["js"], "typescript": ["ts"],
    "c++": [], "c#": [], "sql": [], "rust": [],
    "node.js": ["nodejs"], "django": [], "flask": [], "fastapi": [], "html": [], "css": [],
    "postgresql": ["postgres"], "mysql": [], "mongodb": ["mongo"], "redis": [],
    "aws": ["amazon web services"], "azure": [], "gcp": ["google cloud"],
    "docker": [], "kubernetes": ["k8s"], "terraform": [], "linux": [],
    "git": [], "ci/cd": ["cicd", "ci cd"], "jenkins": [], "github actions": [],
    "graphql": [], "microservices": [],
    "machine learning": [], "deep learning": [], "nlp": ["natural language processing"],
    "pytorch": [], "tensorflow": [], "pandas": [], "numpy": [], "scikit-learn": ["sklearn"],
    "kafka": [], "airflow": [], "tableau": [], "power bi": [],
    "agile": [], "scrum": [], "unit testing": ["unit tests", "pytest", "junit"],
    "data structures": [], "algorithms": [], "object-oriented": ["oop"],
}

_PRE = r"(?:(?<=,)|(?<=, )|(?<=/)|(?<=\()|(?<=: ))"
_END = r"(?=\s*(?:[,.;:/)]|$))"


def _listctx(tok: str) -> list:
    """Match a capitalised ambiguous token only where it reads as a tech-list item:
    'Python, Go, Rust' / 'Go/Python' / '(R)' / 'Python and Go.' but not 'Go above and beyond'."""
    t = re.escape(tok)
    return [
        re.compile(rf"{_PRE}{t}(?![\w&-])"),
        re.compile(rf"(?<![\w-]){t}(?=\s*[,/)])"),
        re.compile(rf"(?:(?<= and )|(?<= or )){t}{_END}", re.M),
    ]


_SPECIAL = {
    "go": [re.compile(r"\bgolang\b", re.I), re.compile(r"\bGo (?:programming|language|lang)\b")]
          + _listctx("Go"),
    "r": [re.compile(r"\bR (?:programming|language)\b"), re.compile(r"\bRStudio\b")]
         + _listctx("R"),
    "rest": [re.compile(r"\bREST\b"), re.compile(r"\brestful\b", re.I),
             re.compile(r"\brest apis?\b", re.I)],
    "excel": [re.compile(r"\bExcel\b(?!\s+(?:in|at|under|when|with)\b)")],
    "spark": [re.compile(r"\b(?:apache spark|pyspark|spark (?:sql|streaming))\b", re.I)]
             + _listctx("Spark"),
    "spring": [re.compile(r"\bSpring (?:Boot|Framework|MVC|Cloud)\b")] + _listctx("Spring"),
    "react": [re.compile(r"\bReact(?:\.js|JS)?\b(?!\s+to\b)"), re.compile(r"\breact\.?js\b", re.I)],
    "node.js": _listctx("Node"),
    "machine learning": [re.compile(r"\bML\b")],
}

_PREFERRED = re.compile(r"preferred|nice to have|bonus|a plus|good to have", re.I)
_REQUIRED = re.compile(r"requirements?|qualifications?|required|must have|you will need|what you.?ll bring", re.I)
_YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?", re.I)


def _pattern(term: str) -> re.Pattern:
    return re.compile(r"(?<![\w+#./-])" + re.escape(term) + r"(?![\w+#-])", re.I)


_PATTERNS = {
    canon: [_pattern(t) for t in [canon, *aliases]] for canon, aliases in VOCAB.items()
}
_ALL = set(_PATTERNS) | set(_SPECIAL)


def extract_skills(text: str) -> set[str]:
    found = set()
    for canon in _ALL:
        pats = _PATTERNS.get(canon, []) + _SPECIAL.get(canon, [])
        if any(p.search(text) for p in pats):
            found.add(canon)
    return found


def parse_jd(jd: str) -> dict:
    """Split JD skills into required vs preferred using section cues; extract years."""
    mode = "required"
    req, pref = set(), set()
    for line in jd.splitlines():
        if _PREFERRED.search(line):
            mode = "preferred"
        elif _REQUIRED.search(line) and len(line) < 60:
            mode = "required"
        (req if mode == "required" else pref).update(extract_skills(line))
    pref -= req
    years = [int(m.group(1)) for m in _YEARS.finditer(jd)]
    return {"required": req, "preferred": pref, "years": max(years) if years else None}
