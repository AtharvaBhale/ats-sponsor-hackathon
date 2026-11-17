from src.app.names import normalize_company
from src.app.staffing import (LcaStats, aggregate_lca, assess, classify_posting,
                              filter_companies)

CONTRACT_POST = "Java Developer. W2 only. Our client is a large bank. 6 month contract."
DIRECT_POST = "Full-time permanent position with benefits. Direct hire."


def test_normalize():
    assert normalize_company("Acme Test Corp.") == "acme test"
    assert normalize_company("Globex & Sons, LLC") == "globex and sons"


def test_strong_name_alone_is_only_possible():
    a = assess("Brightpath Staffing Solutions LLC")
    assert a.level == "possible" and a.score == 40


def test_name_plus_naics_is_likely():
    a = assess("Brightpath Staffing Solutions LLC", naics="561320")
    assert a.level == "likely"


def test_weak_name_never_flags():
    a = assess("Northwind Consulting Group")
    assert a.level == "unlikely" and a.badge() is None


def test_direct_employer_is_clean():
    a = assess("Fabrikam Software Inc", postings=[DIRECT_POST])
    assert a.level == "unlikely" and a.employment_model == "direct_hire"


def test_lca_pattern_flags_without_a_staffing_name():
    lca = LcaStats(n=50, secondary_ratio=0.7, mismatch_ratio=0.9, h1b_dependent=True)
    a = assess("Globex Partners", naics="541511", lca=lca)
    assert a.level == "likely" and any("secondary" in r for r in a.reasons)


def test_small_lca_volume_ignored():
    a = assess("Globex Partners", lca=LcaStats(n=5, secondary_ratio=1.0))
    assert a.score == 0 and a.notes


def test_posting_classification():
    assert classify_posting(CONTRACT_POST)[0] == "contract"
    assert classify_posting(DIRECT_POST)[0] == "direct"
    assert classify_posting("The project meeting is at 3 PM.")[0] == "unknown"


def test_contract_only_model():
    a = assess("Brightpath Staffing Solutions LLC", naics="561320", postings=[CONTRACT_POST])
    assert a.employment_model == "contract_only"


def test_overrides_both_directions():
    ov = {"northwind consulting group": "likely", "brightpath staffing solutions": "unlikely"}
    assert assess("Northwind Consulting Group", overrides=ov).level == "likely"
    assert assess("Brightpath Staffing Solutions LLC", naics="561320", overrides=ov).level == "unlikely"


def test_filters():
    staff = assess("Brightpath Staffing Solutions LLC", naics="561320", postings=[CONTRACT_POST])
    poss = assess("Initech Recruiting Group")
    assert poss.level == "possible"
    direct = assess("Fabrikam Software Inc", postings=[DIRECT_POST])
    items = [{"n": "s", "assessment": staff}, {"n": "p", "assessment": poss},
             {"n": "d", "assessment": direct}]
    names = lambda xs: [i["n"] for i in xs]
    assert names(filter_companies(items)) == ["s", "p", "d"]
    assert names(filter_companies(items, hide_staffing=True)) == ["p", "d"]
    assert names(filter_companies(items, hide_staffing=True, strict=True)) == ["d"]
    assert names(filter_companies(items, direct_hire_only=True)) == ["p", "d"]


def test_aggregate_lca():
    rows = [{"EMPLOYER_NAME": "Globex Talent Partners LLC", "EMPLOYER_STATE": "NJ",
             "WORKSITE_STATE": "TX", "SECONDARY_ENTITY": "Y", "H-1B_DEPENDENT": "Y",
             "NAICS_CODE": "541511"} for _ in range(30)]
    rows += [{"EMPLOYER_NAME": "Globex Talent Partners LLC", "EMPLOYER_STATE": "NJ",
              "WORKSITE_STATE": "NJ", "SECONDARY_ENTITY": "N", "H-1B_DEPENDENT": "Y"}] * 10
    s = aggregate_lca(rows)["globex talent partners"]
    assert s.n == 40 and s.secondary_ratio == 0.75 and s.mismatch_ratio == 0.75
    assert s.h1b_dependent and s.naics == "541511"


def test_api_endpoint():
    from fastapi.testclient import TestClient
    from src.app.main import app
    r = TestClient(app).post("/api/staffing/assess", json={
        "name": "Brightpath Staffing Solutions LLC", "naics": "561320"}).json()
    assert r["level"] == "likely" and r["badge"]["risks"]
