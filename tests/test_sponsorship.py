import csv

import pytest
from fastapi.testclient import TestClient

from src.app import jobs, jobs_store, routes_jobs, sponsor_data, sponsorship
from src.app.main import app
from src.app.sponsorship import classify, posting_signal

USCIS_HDR = ["Fiscal Year", "Employer", "Initial Approval", "Initial Denial",
             "Continuing Approval", "Continuing Denial", "NAICS", "Tax ID", "State", "City", "ZIP"]
LCA_HDR = ["CASE_NUMBER", "CASE_STATUS", "VISA_CLASS", "EMPLOYER_NAME", "EMPLOYER_STATE",
           "WORKSITE_STATE", "SECONDARY_ENTITY", "H-1B_DEPENDENT", "NAICS_CODE"]


def wcsv(path, hdr, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerows(rows)


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    d = tmp_path_factory.mktemp("sp")
    u = []
    for fy in (2021, 2022, 2023, 2024):
        u.append([fy, "Northwind Analytics Inc", 5, 0, 10, 0, "54", "1", "WA", "A", "1"])
    for fy in (2021, 2022, 2023):  # Adatum: 3 good years, but no recent LCAs
        u.append([fy, "Adatum Corp", 5, 0, 10, 0, "54", "2", "WA", "A", "1"])
    for fy in (2021, 2022, 2023, 2024):  # Tailspin: volume but 50% approval rate
        u.append([fy, "Tailspin Toys LLC", 10, 10, 10, 10, "54", "3", "CA", "A", "1"])
    u.append([2024, "Contoso Robotics LLC", 2, 0, 0, 0, "33", "4", "TX", "A", "1"])
    u.append([2019, "Fabrikam Foods Inc", 9, 0, 9, 0, "31", "5", "OH", "A", "1"])
    u.append([2024, "Initrode Software", 4, 0, 0, 0, "54", "6", "WA", "A", "1"])
    wcsv(d / "u.csv", USCIS_HDR, u)
    l = [[f"N{i}", "Certified", "H-1B", "Northwind Analytics Inc", "WA", "WA", "N", "N", "541511"]
         for i in range(30)]
    l += [[f"G{i}", "Certified", "H-1B", "Globex Talent LLC", "NJ", "TX", "Y", "Y", "541511"]
          for i in range(30)]
    l += [[f"T{i}", "Certified", "H-1B", "Tailspin Toys LLC", "CA", "CA", "N", "N", "541512"]
          for i in range(5)]
    wcsv(d / "l.csv", LCA_HDR, l)
    out = d / "s.db"
    sponsor_data.build(out, [(None, d / "u.csv")], [(2024, d / "l.csv")],
                       {"Northwind": "Northwind Analytics Inc"})
    return sponsorship.SponsorDB(out)


def tier(db, name, text="", opt=None):
    return classify(db, name, text, opt)


def test_proven(db):
    r = tier(db, "Northwind Analytics, Inc.")
    assert r["tier"] == "Proven Sponsor" and r["confidence"] == "high"
    assert r["evidence"]["initial_approvals"] == 20 and r["evidence"]["approval_rate"] == 1.0


def test_alias_match(db):
    r = tier(db, "Northwind")
    assert r["tier"] == "Proven Sponsor" and r["match"] == "alias"


def test_good_history_but_no_recent_lca_is_emerging(db):
    r = tier(db, "Adatum Corp")
    assert r["tier"] == "Emerging Sponsor" and any("No certified LCAs" in x for x in r["reasons"])


def test_low_approval_rate_is_emerging(db):
    r = tier(db, "Tailspin Toys")
    assert r["tier"] == "Emerging Sponsor" and any("below" in x for x in r["reasons"])


def test_small_volume_is_emerging(db):
    assert tier(db, "Contoso Robotics")["tier"] == "Emerging Sponsor"


def test_lapsed_sponsor_is_non_sponsor_medium_confidence(db):
    r = tier(db, "Fabrikam Foods")
    assert r["tier"] == "Non-Sponsor" and r["confidence"] == "medium"
    assert any("FY2019" in x for x in r["reasons"])


def test_unmatched_is_non_sponsor_low_confidence(db):
    r = tier(db, "Zzyzx Labs")
    assert r["tier"] == "Non-Sponsor" and r["confidence"] == "low"


def test_opt_only_from_posting_or_list(db):
    assert tier(db, "Zzyzx Labs", "STEM OPT students welcome to apply")["tier"] == "OPT-Only"
    assert tier(db, "Zzyzx Labs", "", {"zzyzx labs"})["tier"] == "OPT-Only"


def test_posting_refusal_overrides_per_role(db):
    r = tier(db, "Northwind Analytics", "We are unable to sponsor visas at this time.")
    assert r["tier"] == "Proven Sponsor" and r["effective_tier"] == "Non-Sponsor (this role)"
    assert r["role_note"]


def test_longer_legal_name_is_unknown_not_non_sponsor(db):
    # job says "Initrode"; filings say "Initrode Software": never call that a Non-Sponsor
    r = tier(db, "Initrode")
    assert r["tier"] == "Unknown" and r["related_entities"] == ["Initrode Software"]
    assert "alias" in r["reasons"][0]


def test_alias_resolves_the_ambiguity(db):
    assert tier(db, "Northwind")["related_entities"] == []


def test_database_missing_is_unknown_not_non_sponsor():
    r = classify(None, "Anything")
    assert r["tier"] == "Unknown" and r["confidence"] == "none"


def test_lca_stats_feed_staffing_detector(db):
    p = db.profile("Globex Talent LLC")
    s = p.lca_stats()
    assert s.n == 30 and s.secondary_ratio == 1.0 and s.mismatch_ratio == 1.0 and s.h1b_dependent
    from src.app.staffing import assess
    assert assess("Globex Talent LLC", naics=p.naics, lca=s).level == "likely"


@pytest.mark.parametrize("text,expected", [
    ("We are unable to sponsor visas at this time.", "no_sponsorship"),
    ("Will not provide visa sponsorship.", "no_sponsorship"),
    ("No visa sponsorship is available for this role.", "no_sponsorship"),
    ("Must be authorized to work in the US without requiring sponsorship.", "no_sponsorship"),
    ("Candidates must not require sponsorship now or in the future.", "no_sponsorship"),
    ("We do not sponsor H-1B visas.", "no_sponsorship"),
    ("Visa sponsorship is available for qualified candidates.", "offers"),
    ("We will sponsor H-1B for the right person.", "offers"),
    ("H-1B transfer is supported.", "offers"),
    ("Open to STEM OPT and CPT candidates.", "opt_ok"),
    ("F-1 students with OPT work authorization welcome.", "opt_ok"),
    ("Opt in to our newsletter.", "unknown"),
    ("The project meeting is scheduled for 3:00 PM.", "unknown"),
    ("Sponsor a community event as part of the role.", "unknown"),
])
def test_posting_signal(text, expected):
    assert posting_signal(text) == expected, text


def test_api_tier_and_ingest_integration(db, monkeypatch):
    import httpx
    sponsorship.set_db(db)
    routes_jobs.set_store(jobs_store.JobStore())
    gh = {"title": "Data Engineer", "location": {"name": "Seattle"}, "company_name": "Northwind Analytics",
          "content": "&lt;p&gt;Python and SQL&lt;/p&gt;"}
    monkeypatch.setattr(routes_jobs, "make_client", lambda: httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=gh))))
    from src.app import urlsafe
    monkeypatch.setattr(urlsafe, "RESOLVER", lambda h, p, type=0: [(2, 1, 6, "", ("93.184.216.34", p))])
    c = TestClient(app)
    r = c.post("/api/sponsorship/tier", json={"company": "Northwind Analytics"}).json()
    assert r["tier"] == "Proven Sponsor"
    ing = c.post("/api/jobs/ingest", json={"url": "https://boards.greenhouse.io/nw/jobs/1"}).json()
    assert ing["sponsorship"]["tier"] == "Proven Sponsor"
    assert c.get("/api/jobs?tiers=Proven Sponsor").json()[0]["sponsorship"]["tier"] == "Proven Sponsor"
    assert c.get("/api/jobs?tiers=Non-Sponsor").json() == []
    assert c.get("/api/sponsorship/status").json()["loaded"] is True
    sponsorship.set_db(None)
