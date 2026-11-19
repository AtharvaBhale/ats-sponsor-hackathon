"""Find, read, and replace \\item bullets in a LaTeX resume without touching anything else."""
import re

ITEM = re.compile(r"^(?P<pre>[ \t]*\\item(?:\[[^\]]*\])?[ \t]+)(?P<text>.+?)[ \t]*$", re.M)
_ESC = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}


def escape(s: str) -> str:
    return "".join(_ESC.get(c, c) for c in s)


def latex_to_text(s: str) -> str:
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = re.sub(r"\\(?:textbf|textit|emph|underline|texttt|textsc)\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:hfill|\\|quad|qquad)", " ", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", s)
    s = re.sub(r"\\([&%$#_{}])", r"\1", s).replace("{", " ").replace("}", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def extract_bullets(tex: str) -> list:
    """[(start, end, raw_text)] for each \\item line body, in document order."""
    return [(m.start("text"), m.end("text"), m.group("text")) for m in ITEM.finditer(tex)]


def replace_bullets(tex: str, new_text: dict) -> str:
    """new_text: {bullet_index: plain text}. Text is LaTeX-escaped; other bullets untouched."""
    spans = extract_bullets(tex)
    for i in sorted(new_text, reverse=True):
        s, e, _ = spans[i]
        tex = tex[:s] + escape(new_text[i]) + tex[e:]
    return tex
