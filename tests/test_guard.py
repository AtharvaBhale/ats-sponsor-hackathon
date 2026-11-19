from src.app.guard import check

EVIDENCE = ("Software Intern at Acme Test Corp. Built a REST API in Python for an internal "
            "inventory tool. Wrote unit tests that raised coverage. B.S. Computer Science.")


def test_faithful_rewrite_passes():
    r = check("Developed a Python REST API for Acme Test Corp's inventory tool.", EVIDENCE)
    assert r.ok, r.violations


def test_invented_number_rejected():
    r = check("Built a Python REST API that cut latency by 40%.", EVIDENCE)
    assert not r.ok and any("40" in x for x in r.violations)


def test_invented_skill_rejected():
    r = check("Built a Python REST API deployed on Kubernetes.", EVIDENCE)
    assert any("kubernetes" in x for x in r.violations)


def test_invented_degree_rejected():
    r = check("Applied M.S. coursework to build a Python REST API.", EVIDENCE)
    assert any("degree" in x for x in r.violations)


def test_invented_employer_rejected():
    r = check("Built a Python REST API at Globex.", EVIDENCE)
    assert any("Globex" in x for x in r.violations)


def test_invented_certification_rejected():
    r = check("Certified engineer who built a Python REST API.", EVIDENCE)
    assert any("certification" in x for x in r.violations)


def test_user_confirmed_addition_is_allowed():
    r = check("Built a Kubernetes-deployed Python REST API.", EVIDENCE + " Course project: deployed on Kubernetes.")
    assert r.ok, r.violations


def test_inflection_of_evidence_word_is_not_a_new_name():
    ev = "Built a REST API in Python for an internal inventory tool."
    assert check("Built a RESTful API in Python for an internal inventory tool.", ev).ok


def test_invented_company_near_an_evidence_word_still_blocked():
    ev = "Built a REST API in Python at Acme."
    r = check("Built a REST API in Python at Acmeville Industries.", ev)
    assert any("Acmeville" in x for x in r.violations)
