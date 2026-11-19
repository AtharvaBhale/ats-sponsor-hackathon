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


def insert_bullet(tex: str, text: str, section: str = "Projects") -> str:
    """Add an \\item under the named section (creating it if absent)."""
    item = "  \\item " + escape(text) + "\n"
    m = re.search(r"\\section\*?\{[^}]*" + re.escape(section) + r"[^}]*\}", tex, re.I)
    if m:
        end = tex.find("\\end{itemize}", m.end())
        nxt = re.search(r"\\section", tex[m.end():])
        if end != -1 and (not nxt or end < m.end() + nxt.start()):
            return tex[:end] + item + tex[end:]
        return tex[:m.end()] + "\n\\begin{itemize}\n" + item + "\\end{itemize}" + tex[m.end():]
    block = "\\section*{" + section + "}\n\\begin{itemize}\n" + item + "\\end{itemize}\n"
    i = tex.rfind("\\end{document}")
    return tex[:i] + block + tex[i:] if i != -1 else tex + "\n" + block
