"""Extract text from uploaded resumes/transcripts/certificates and screen evidence."""
import io
import re
from pathlib import Path

from .skills import extract_skills

MAX_BYTES = 5_000_000
MAX_PAGES = 20


class ParseError(Exception):
    pass


def _norm(text: str) -> str:
    text = text.replace("\r", "\n").replace("\x00", "")
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def extract_text(filename: str, data: bytes) -> tuple:
    """Returns (text, warnings). Raises ParseError for unsupported/unreadable files."""
    if len(data) > MAX_BYTES:
        raise ParseError("File too large (5 MB max)")
    ext, warnings = Path(filename or "").suffix.lower(), []
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ParseError("Encrypted PDFs are not supported")
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:MAX_PAGES])
            if len(text.strip()) < 40:
                warnings.append("No selectable text found (scanned PDF?). OCR is not supported; "
                                "paste the text instead.")
        elif ext == ".docx":
            from docx import Document
            doc = Document(io.BytesIO(data))
            cells = [c.text for t in doc.tables for r in t.rows for c in r.cells]
            text = "\n".join([p.text for p in doc.paragraphs] + cells)
        elif ext in (".txt", ".md", ".tex"):
            text = data.decode("utf-8", errors="replace")
        else:
            raise ParseError(f"Unsupported file type '{ext}'. Use PDF, DOCX, TXT, MD or TEX.")
    except ParseError:
        raise
    except Exception as e:  # corrupt files raise many different library errors
        raise ParseError(f"Could not read this file: {type(e).__name__}")
    return _norm(text), warnings


_PII = [re.compile(p, re.I) for p in (
    r"\b\d{3}-\d{2}-\d{4}\b", r"\bstudent\s*(?:id|no\.?|number|#)", r"\b(?:dob|date of birth)\b",
    r"\b\d{9}\b", r"\bpassport\b", r"\b(?:a|alien)[- ]?number\b")]
_COURSE = re.compile(r"\b(course|coursework|certificate|certified|certification|project|thesis|"
                     r"capstone|lab|research|internship)\b", re.I)


def screen_evidence(text: str, jd: str) -> dict:
    """Keep lines relevant to the job; drop personal identifiers and unrelated lines."""
    jd_skills = extract_skills(jd)
    jd_words = {w for w in re.findall(r"[a-z]{5,}", jd.lower())}
    kept, seen, pii, irrelevant = [], set(), 0, 0
    for line in (l.strip() for l in text.splitlines()):
        if len(line) < 8:
            continue
        if any(p.search(line) for p in _PII):
            pii += 1
            continue
        skills = extract_skills(line)
        relevant = bool(skills & jd_skills) or (
            bool(_COURSE.search(line)) and bool(jd_words & set(re.findall(r"[a-z]{5,}", line.lower()))))
        if not relevant:
            irrelevant += 1
        elif line.lower() not in seen:
            seen.add(line.lower())
            kept.append(line)
    return {"kept": kept[:40], "dropped_irrelevant": irrelevant, "dropped_personal_ids": pii}
