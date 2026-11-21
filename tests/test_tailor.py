import asyncio

from fastapi.testclient import TestClient

from src.app import latex_resume as lr, routes_tailor, tailor
from src.app.main import app

TEX = open("templates/resume.tex").read()
JD = "Requirements\nPython, REST, Docker\n"


def run(coro):
    return asyncio.run(coro)


def test_extract_and_replace_only_touch_bullets():
    b = lr.extract_bullets(TEX)
    assert [x[2] for x in b] == ["Built a REST API for an internal inventory tool.",
                                 "Wrote unit tests that raised coverage."]
    out = lr.replace_bullets(TEX, {1: "Tested 50% & more_stuff"})
    assert r"Tested 50\% \& more\_stuff" in out and out.count("\\item") == 2
    assert out.replace(r"Tested 50\% \& more\_stuff", "Wrote unit tests that raised coverage.") == TEX


def test_latex_to_text_and_escape():
    assert lr.latex_to_text(r"\textbf{Intern}, Acme \& Co \hfill 2023") == "Intern, Acme & Co 2023"
    assert lr.escape("a_b & 5%") == r"a\_b \& 5\%"


def test_clean_llm_output():
    assert tailor.clean('Rewritten bullet: - "Built an API."\nextra') == "Built an API."


def test_guarded_rewrites_accept_faithful_reject_fabricated():
    outs = iter(["Developed a REST API for an internal inventory tool.",
                 "Wrote unit tests, cutting bugs by 60% on Kubernetes."])
    async def fake(bullet, allowed):
        return next(outs)
    r = run(tailor.tailor(TEX, JD, None, fake))
    b = r["bullets"]
    assert b[0]["accepted"] and not b[1]["accepted"]
    assert any("60" in v for v in b[1]["violations"]) and any("kubernetes" in v for v in b[1]["violations"])
    assert "Developed a REST API" in r["tex"] and "Wrote unit tests that raised coverage." in r["tex"]
    assert r["summary"]["accepted"] == 1 and r["summary"]["rejected"] == 1


def test_gap_reports_missing_and_additions_become_evidence():
    async def same(bullet, allowed):
        return bullet
    base = run(tailor.tailor(TEX, JD, None, same))
    assert "docker" in base["gap"]["missing_required"] and base["gap"]["questions"]
    more = run(tailor.tailor(TEX, JD, ["Course project: containerized a Flask app with Docker."], same))
    assert "docker" not in more["gap"]["missing_required"]


def test_user_addition_lets_a_rewrite_use_that_skill():
    async def uses_docker(bullet, allowed):
        return "Built a REST API for an inventory tool, containerized with Docker."
    no = run(tailor.tailor(TEX, JD, None, uses_docker))["bullets"][0]
    yes = run(tailor.tailor(TEX, JD, ["Course project: containerized an app with Docker."], uses_docker))["bullets"][0]
    assert not no["accepted"] and yes["accepted"]


def test_empty_and_overlong_rewrites_rejected():
    async def bad(bullet, allowed):
        return "" if "REST" in bullet else "Wrote " + "very " * 60 + "good tests."
    r = run(tailor.tailor(TEX, JD, None, bad))["bullets"]
    assert r[0]["violations"] == ["empty rewrite"] and "longer" in r[1]["violations"][0]


def test_api_ok_and_validation(monkeypatch):
    async def fake(bullet, allowed):
        return bullet
    monkeypatch.setattr(routes_tailor, "rewrite_fn", fake)
    c = TestClient(app)
    ok = c.post("/api/tailor", json={"resume_latex": TEX, "job_description": JD}).json()
    assert ok["summary"]["bullets"] == 2 and "tex" in ok
    assert c.post("/api/tailor", json={"resume_latex": "", "job_description": JD}).status_code == 400


JAKE = r"""\documentclass{article}
\newcommand{\resumeItem}[1]{\item\small{#1 \vspace{-2pt}}}
\newcommand{\bullet2}[1]{\item #1}
\newcommand{\resumeSubheading}[2]{\vspace{-2pt}\item
  \textbf{#1} & #2 \\}
\begin{document}
\section{Experience}
\resumeSubheading{Data Scientist}{Apr 2026 -- Present}
\begin{itemize}
  \resumeItem{Built ETL pipelines in Python, cutting runtime by \textbf{40\%}.}
  \resumeItem{Mentored a team of 3 developers across
    two projects with {nested braces} intact.}
  \item Plain item still works.
\end{itemize}
\end{document}
"""


def test_macro_bullets_found_in_body_only():
    b = lr.extract_bullets(JAKE)
    texts = [lr.latex_to_text(x[2], collapse=True) for x in b]
    assert texts == ["Built ETL pipelines in Python, cutting runtime by 40%.",
                     "Mentored a team of 3 developers across two projects with nested braces intact.",
                     "Plain item still works."]


def test_macro_bullet_replacement_keeps_everything_else():
    out = lr.replace_bullets(JAKE, {0: "Built Python ETL pipelines & cut runtime by 40%."})
    assert r"\resumeItem{Built Python ETL pipelines \& cut runtime by 40\%.}" in out
    assert r"\newcommand{\resumeItem}[1]{\item\small{#1 \vspace{-2pt}}}" in out
    assert out.count(r"\resumeItem{") == 2 and "nested braces" in out


def test_custom_macro_defined_with_newcommand_is_detected():
    assert "bullet2" in lr.bullet_macros(JAKE) and "resumeItem" in lr.bullet_macros(JAKE)


def test_tailor_processes_macro_resume():
    async def fake(bullet, allowed):
        return bullet.replace("Built", "Developed")
    r = run(tailor.tailor(JAKE, "Requirements\nPython", None, fake))
    assert r["summary"]["bullets"] == 3 and r["bullets"][0]["accepted"]
    assert r"\resumeItem{Developed ETL pipelines in Python" in r["tex"]
    assert r["tex"].count("\\resumeItem{") == 2
