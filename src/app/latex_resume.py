"""Find, read, and replace \\item bullets in a LaTeX resume without touching anything else."""
import re

ITEM = re.compile(r"^(?P<pre>[ \t]*\\item(?:\[[^\]]*\])?[ \t]+)(?P<text>.+?)[ \t]*$", re.M)
_ESC = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"}


def escape(s: str) -> str:
    return "".join(_ESC.get(c, c) for c in s)


def latex_to_text(s: str, collapse: bool = False) -> str:
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = re.sub(r"\\(?:textbf|textit|emph|underline|texttt|textsc)\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:hfill|\\|quad|qquad)", " ", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", s)
    s = re.sub(r"\\([&%$#_{}])", r"\1", s).replace("{", " ").replace("}", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return (re.sub(r"\s+", " ", s) if collapse else s).strip()


def body_start(tex: str) -> int:
    m = re.search(r"\\begin\{document\}", tex)
    return m.end() if m else 0


def body_text(tex: str) -> str:
    """Resume content only: everything after \\begin{document} (no preamble or macro definitions)."""
    return tex[body_start(tex):]


def bullet_macros(tex: str) -> set:
    """Macros that render a bullet: resumeItem plus any \\newcommand{\\x}[1]{\\item ...}."""
    return {"resumeItem"} | set(re.findall(r"\\(?:re)?newcommand\{\\(\w+)\}\[1\]\{\s*\\item", tex))


def _match_brace(tex: str, i: int) -> int:
    depth, j = 0, i
    while j < len(tex):
        c = tex[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def extract_bullets(tex: str) -> list:
    """[(start, end, raw_text)] for each bullet body in the resume, in document order.
    Recognizes \\item lines and custom bullet macros such as \\resumeItem{...} (multi-line ok)."""
    start = body_start(tex)
    spans = [(m.start("text"), m.end("text"), m.group("text")) for m in ITEM.finditer(tex, start)]
    names = bullet_macros(tex)
    pat = re.compile(r"\\(?:" + "|".join(re.escape(n) for n in names) + r")\s*\{")
    for m in pat.finditer(tex, start):
        close = _match_brace(tex, m.end() - 1)
        if close != -1:
            spans.append((m.end(), close, tex[m.end():close]))
    return sorted(spans)


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
