"""LaTeX compilation: no shell, timeout, input blocklist."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

TIMEOUT_S = 20
MAX_BYTES = 200_000

# Constructs that read/write arbitrary files or run commands.
BLOCKED = [
    r"\\write18", r"\\immediate\s*\\write", r"\\openin", r"\\openout",
    r"\\input\s*\{?\s*[/~.]", r"\\include\s*\{?\s*[/~.]",
    r"\\usepackage\s*\{shellesc\}", r"\\catcode", r"\\read\b", r"\\directlua",
]


class LatexError(Exception):
    pass


def validate(source: str) -> None:
    if len(source.encode()) > MAX_BYTES:
        raise LatexError("Source too large")
    for pat in BLOCKED:
        if re.search(pat, source):
            raise LatexError(f"Blocked LaTeX construct: {pat}")


def compile_pdf(source: str) -> bytes:
    validate(source)
    if not shutil.which("tectonic"):
        raise LatexError("tectonic is not installed (see scripts/setup.sh)")
    with tempfile.TemporaryDirectory() as d:
        tex = Path(d) / "resume.tex"
        tex.write_text(source, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["tectonic", "--chatter", "minimal", "resume.tex"],
                cwd=d, capture_output=True, text=True, timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            raise LatexError("Compile timed out")
        pdf = Path(d) / "resume.pdf"
        if proc.returncode != 0 or not pdf.exists():
            raise LatexError(proc.stderr[-1500:] or "Compile failed")
        return pdf.read_bytes()
