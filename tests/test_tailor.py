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
