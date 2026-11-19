"""Plain resume text -> simple ATS-safe LaTeX, and LaTeX -> plain text / Markdown."""
import re

from .latex_resume import escape, latex_to_text

HEAD = (r"\documentclass[10pt]{article}" "\n" r"\usepackage[margin=0.75in]{geometry}" "\n"
        r"\pagenumbering{gobble}" "\n" r"\begin{document}" "\n")
_KNOWN = re.compile(r"^(summary|objective|profile|education|experience|work experience|"
                    r"professional experience|projects|skills|technical skills|certifications?|"
                    r"coursework|awards|publications|activities|leadership)\s*:?$", re.I)
_BULLET = re.compile(r"^[-•*·▪●‣]\s*")


def _heading(line: str) -> bool:
    s = line.strip()
    return bool(_KNOWN.match(s)) or (3 <= len(s) <= 32 and s.isupper() and re.fullmatch(r"[A-Z &/]+", s))


def text_to_latex(text: str) -> str:
    lines = [l.rstrip() for l in text.splitlines()]
    out, in_list, started, contact = [HEAD], False, False, []
    nonblank = [l for l in lines if l.strip()]
    if not nonblank:
        return HEAD + "\\end{document}\n"
    name, rest = nonblank[0].strip(), nonblank[1:]
    for l in rest:
        if _heading(l):
            break
        contact.append(l.strip())
    out.append("\\begin{center}{\\Large \\textbf{" + escape(name) + "}}"
               + "".join("\\\\ " + escape(c) for c in contact[:3]) + "\\end{center}\n")
    skip = set(range(len(contact[:3])))
    for i, l in enumerate(rest):
        s = l.strip()
        if not s or i in skip and not started:
            continue
        if _heading(s):
            if in_list:
                out.append("\\end{itemize}"); in_list = False
            out.append("\\section*{" + escape(s.rstrip(":").title() if s.isupper() else s.rstrip(":")) + "}")
            started = True
        elif _BULLET.match(s):
            if not in_list:
                out.append("\\begin{itemize}"); in_list = True
            out.append("  \\item " + escape(_BULLET.sub("", s)))
        else:
            if in_list:
                out.append("\\end{itemize}"); in_list = False
            out.append(escape(s) + "\\\\")
    if in_list:
        out.append("\\end{itemize}")
    out.append("\\end{document}\n")
    return "\n".join(out)


def tex_to_plain(tex: str, markdown: bool = False) -> str:
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", tex, re.S)
    body, out, first = (m.group(1) if m else tex), [], True
    for raw in body.splitlines():
        s = re.sub(r"\\begin\{[^}]*\}|\\end\{[^}]*\}", "", raw).strip()
        for part in (p.strip() for p in s.split("\\\\")):
            if not part:
                continue
            sec = re.match(r"\\section\*?\{(.*)\}", part)
            item = re.match(r"\\item(?:\[[^\]]*\])?\s*(.*)", part)
            if sec:
                t = latex_to_text(sec.group(1))
                out += ["", ("## " + t) if markdown else t.upper()]
            elif item:
                out.append("- " + latex_to_text(item.group(1)))
            else:
                t = latex_to_text(part)
                if t:
                    out.append(("# " + t) if (markdown and first) else t)
                    first = False
    return "\n".join(out).strip() + "\n"
