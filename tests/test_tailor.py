import asyncio

from fastapi.testclient import TestClient

from src.app import keywords as kw, latex_resume as lr, routes_tailor, tailor
from src.app.main import app

TEX = open("templates/resume.tex").read()
JD = "Requirements\nREST API experience\nInventory systems\nUnit testing and coverage metrics\n"
JD_SKILLS = "Requirements\nPython, REST, Docker\n"
FINANCE_JD = ("Requirements\nFinancial modeling, valuation and portfolio analysis\n"
              "Energy infrastructure investing and asset management\n")


def run(coro):
    return asyncio.run(coro)


def fake_outputs(*outs):
    it = iter(outs)

    async def fn(bullet, allowed):
        return next(it)
    return fn


def test_extract_and_replace_only_touch_bullets():
    b = lr.extract_bullets(TEX)
    assert [x[2] for x in b] == ["Built a REST API for an internal inventory tool.",
                                 "Wrote unit tests that raised coverage."]
    out = lr.replace_bullets(TEX, {1: "Tested 50% & more_stuff"})
    assert r"Tested 50\% \& more\_stuff" in out and out.count("\\item") == 2


def test_latex_to_text_and_escape():
    assert lr.latex_to_text(r"\textbf{Intern}, Acme \& Co \hfill 2023") == "Intern, Acme & Co 2023"
    assert lr.escape("a_b & 5%") == r"a\_b \& 5\%"


def test_clean_llm_output():
    assert tailor.clean('Rewritten bullet: - "Built an API."\nextra') == "Built an API."


# ---- keyword fit
def test_fit_weak_for_unrelated_job_and_strong_for_related():
    ev = lr.latex_to_text(lr.body_text(TEX))
    assert kw.fit(FINANCE_JD, ev)["level"] == "weak" and kw.fit(FINANCE_JD, ev)["matched_stems"] == []
    good = kw.fit(JD, ev)
    assert good["level"] in ("strong", "partial") and "inventory" in good["matched"]
    assert kw.fit("", ev)["score"] is None


def test_gained_counts_only_truthful_new_keywords():
    allowed = {"inventory", "rest"}
    assert kw.gained("Wrote unit tests.", "Wrote unit tests for the inventory REST API.", allowed) == ["inventory", "rest"]
    assert kw.gained("Built a REST API.", "Built a REST API.", allowed) == []
    assert kw.gained("Built it.", "Built it with Kubernetes.", allowed) == []  # not allowed -> no credit


# ---- tailoring rules
def test_cosmetic_rewrite_is_not_accepted():
    r = run(tailor.tailor(TEX, JD, None, fake_outputs("Built a REST API for internal inventory tool.", "Wrote unit tests.")))
    b = r["bullets"]
    assert not b[0]["accepted"] and not b[0]["violations"] and "No new job keyword" in b[0]["note"]
    assert r["tex"] == TEX and r["summary"]["accepted"] == 0


def test_rewrite_that_adds_a_truthful_keyword_is_accepted():
    r = run(tailor.tailor(TEX, JD, None, fake_outputs(
        "Built a REST API for an internal inventory tool.",
        "Wrote unit tests that raised coverage for the inventory REST API.")))
    b = r["bullets"]
    assert b[1]["accepted"] and set(b[1]["gained"]) == {"inventory", "rest"}
    assert "coverage for the inventory REST API." in r["tex"] and r["summary"]["accepted"] == 1


def test_fabricated_rewrite_is_blocked():
    r = run(tailor.tailor(TEX, JD, None, fake_outputs(
        "Built a REST API for an internal inventory tool, cutting latency by 40% on Kubernetes.", "Wrote unit tests.")))
    v = r["bullets"][0]["violations"]
    assert any("40" in x for x in v) and any("kubernetes" in x for x in v)
    assert r["tex"] == TEX and r["summary"]["rejected"] == 1


def test_unrelated_job_changes_nothing_and_never_calls_the_model():
    async def must_not_run(bullet, allowed):
        raise AssertionError("model should not be called")
    r = run(tailor.tailor(TEX, FINANCE_JD, None, must_not_run))
    assert r["tex"] == TEX and r["summary"]["accepted"] == 0
    assert "nothing truthful to add" in r["summary"]["skipped_reason"] and r["fit"]["level"] == "weak"


def test_gap_reports_missing_and_additions_become_evidence():
    same = fake_outputs("a", "b")
    base = run(tailor.tailor(TEX, JD_SKILLS, None, lambda *a: asyncio.sleep(0, "")))
    assert "docker" in base["gap"]["missing_required"] and base["gap"]["questions"]
    more = run(tailor.tailor(TEX, JD_SKILLS, ["Course project: containerized a Flask app with Docker."], lambda *a: asyncio.sleep(0, "")))
    assert "docker" not in more["gap"]["missing_required"]


def test_user_addition_lets_a_rewrite_use_that_skill():
    out = "Built a REST API for an inventory tool, containerized with Docker."
    no = run(tailor.tailor(TEX, JD_SKILLS, None, fake_outputs(out, "x")))["bullets"][0]
    yes = run(tailor.tailor(TEX, JD_SKILLS, ["Course project: containerized an app with Docker."], fake_outputs(out, "x")))["bullets"][0]
    assert not no["accepted"] and no["violations"] and yes["accepted"] and "docker" in yes["gained"]


def test_empty_and_overlong_rewrites_rejected():
    async def bad(bullet, allowed):
        return "" if "REST" in bullet else "Wrote " + "very " * 60 + "good tests."
    r = run(tailor.tailor(TEX, JD_SKILLS, None, bad))["bullets"]
    assert r[0]["violations"] == ["empty rewrite"] and "longer" in r[1]["violations"][0]


def test_api_ok_and_validation(monkeypatch):
    async def same(bullet, allowed):
        return bullet
    monkeypatch.setattr(routes_tailor, "rewrite_fn", same)
    c = TestClient(app)
    ok = c.post("/api/tailor", json={"resume_latex": TEX, "job_description": JD}).json()
    assert ok["summary"]["bullets"] == 2 and "tex" in ok and "fit" in ok
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
    texts = [lr.latex_to_text(x[2], collapse=True) for x in lr.extract_bullets(JAKE)]
    assert texts == ["Built ETL pipelines in Python, cutting runtime by 40%.",
                     "Mentored a team of 3 developers across two projects with nested braces intact.",
                     "Plain item still works."]


def test_macro_bullet_replacement_keeps_everything_else():
    out = lr.replace_bullets(JAKE, {0: "Built Python ETL pipelines & cut runtime by 40%."})
    assert r"\resumeItem{Built Python ETL pipelines \& cut runtime by 40\%.}" in out
    assert r"\newcommand{\resumeItem}[1]{\item\small{#1 \vspace{-2pt}}}" in out
    assert out.count(r"\resumeItem{") == 2 and "nested braces" in out


def test_custom_macro_defined_with_newcommand_is_detected():
    assert {"bullet2", "resumeItem"} <= lr.bullet_macros(JAKE)


def test_tailor_processes_macro_resume():
    async def fn(bullet, allowed):
        return bullet.rstrip(".") + " using Python." if "Mentored" in bullet else bullet
    r = run(tailor.tailor(JAKE, "Requirements\nPython", None, fn))
    assert r["summary"]["bullets"] == 3 and r["bullets"][1]["accepted"]
    assert r"\resumeItem{Mentored a team of 3 developers across two projects with nested braces intact using Python.}" in r["tex"]
    assert r["tex"].count("\\resumeItem{") == 2


def test_rewrite_that_drops_a_skill_is_blocked_even_if_it_adds_a_keyword():
    # the real bad case: "REST API" deleted, a weaker verb swapped in, a different keyword added
    r = run(tailor.tailor(TEX, JD, None, fake_outputs(
        "Interned in the development of an internal inventory tool with coverage reports.", "Wrote unit tests.")))
    b = r["bullets"][0]
    assert not b["accepted"] and b["violations"] == ["drops from the original: rest"]
    assert r["tex"] == TEX


def test_rewrite_that_drops_a_number_is_blocked():
    async def fn(bullet, allowed):
        return "Built ETL pipelines in Python and Docker." if "ETL" in bullet else bullet
    r = run(tailor.tailor(JAKE, "Requirements\nPython, Docker", ["Course project: used Docker."], fn))
    assert any("40" in v for v in r["bullets"][0]["violations"])
