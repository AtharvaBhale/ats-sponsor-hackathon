"""Deterministic skill/keyword extraction. No LLM: fast, testable, explainable."""
import re

# Seed vocabulary (extend as you test). canonical name -> aliases
VOCAB = {
    "python": [], "java": [], "javascript": ["js"], "typescript": ["ts"],
    "c++": [], "c#": [], "go": ["golang"], "rust": [], "sql": [], "r": [],
    "react": ["react.js", "reactjs"], "node.js": ["nodejs", "node"], "django": [],
    "flask": [], "fastapi": [], "spring": ["spring boot"], "html": [], "css": [],
    "postgresql": ["postgres"], "mysql": [], "mongodb": ["mongo"], "redis": [],
    "aws": ["amazon web services"], "azure": [], "gcp": ["google cloud"],
    "docker": [], "kubernetes": ["k8s"], "terraform": [], "linux": [],
    "git": [], "ci/cd": ["cicd", "ci cd"], "jenkins": [], "github actions": [],
    "rest": ["rest api", "restful"], "graphql": [], "microservices": [],
    "machine learning": ["ml"], "deep learning": [], "nlp": ["natural language processing"],
    "pytorch": [], "tensorflow": [], "pandas": [], "numpy": [], "scikit-learn": ["sklearn"],
    "spark": ["pyspark"], "kafka": [], "airflow": [], "tableau": [], "power bi": [],
    "excel": [], "agile": [], "scrum": [], "unit testing": ["unit tests", "pytest", "junit"],
    "data structures": [], "algorithms": [], "object-oriented": ["oop"],
}

_PREFERRED = re.compile(r"preferred|nice to have|bonus|a plus|good to have", re.I)
_REQUIRED = re.compile(r"requirements?|qualifications?|required|must have|you will need|what you.?ll bring", re.I)
_YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?years?", re.I)


def _pattern(term: str) -> re.Pattern:
    return re.compile(r"(?<![\w+#./-])" + re.escape(term) + r"(?![\w+#-])", re.I)


_PATTERNS = {
    canon: [_pattern(t) for t in [canon, *aliases]] for canon, aliases in VOCAB.items()
}


def extract_skills(text: str) -> set[str]:
    found = set()
    for canon, pats in _PATTERNS.items():
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
