import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from src.app import jobs, jobs_store, routes_jobs, urlsafe
from src.app.htmltext import html_to_text
from src.app.main import app


def public_resolver(host, port, type=0):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def private_resolver(host, port, type=0):
    return [(2, 1, 6, "", ("10.0.0.5", port))]


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


GH_URL = "https://boards.greenhouse.io/fictionalco/jobs/12345"
LEVER_URL = "https://jobs.lever.co/fictionalco/abc-123"
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)

GH_JSON = {"title": "Backend Engineer", "location": {"name": "Remote, US"},
           "updated_at": "2026-11-10T09:00:00-05:00",
           "content": "&lt;p&gt;Requirements&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python and SQL&lt;/li&gt;&lt;/ul&gt;"}
LEVER_JSON = {"text": "Data Analyst", "categories": {"location": "Austin, TX"},
              "descriptionPlain": "Analyze data.",
              "lists": [{"text": "Requirements", "content": "<li>SQL</li><li>Excel</li>"}],
              "createdAt": int((NOW - timedelta(days=100)).timestamp() * 1000)}


# ---------- portal detection
def test_detect_portals():
    g = jobs.detect_portal(GH_URL)
    assert (g.kind, g.company, g.job_id) == ("greenhouse", "fictionalco", "12345")
    assert g.api_url == "https://boards-api.greenhouse.io/v1/boards/fictionalco/jobs/12345"
    assert jobs.detect_portal("https://job-boards.greenhouse.io/fictionalco/jobs/9").kind == "greenhouse"
    l = jobs.detect_portal(LEVER_URL)
    assert l.api_url == "https://api.lever.co/v0/postings/fictionalco/abc-123"
    assert jobs.detect_portal("https://acme.wd5.myworkdayjobs.com/site/job/x").kind == "workday"
    assert jobs.detect_portal("https://example.com/careers/1").kind == "other"
    assert jobs.detect_portal("https://boards.greenhouse.io/fictionalco").kind == "other"


# ---------- SSRF protection
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://10.1.2.3/", "http://169.254.169.254/latest/meta-data",
    "http://[::1]/", "http://0.0.0.0/", "file:///etc/passwd", "ftp://example.com/x",
    "https://user:pw@example.com/", "https://example.com:8080/", "http://100.64.0.1/",
])
def test_blocks_unsafe_urls(url):
    with pytest.raises(urlsafe.UnsafeURL):
        urlsafe.validate_url(url, public_resolver)


def test_blocks_hostname_resolving_to_private_ip():
    with pytest.raises(urlsafe.UnsafeURL):
        urlsafe.validate_url("https://innocent.example.com/", private_resolver)


def test_blocks_redirect_to_private_ip():
    def handler(req):
        if req.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        return httpx.Response(200, text="secret")
    def resolver(host, port, type=0):
        ip = "169.254.169.254" if host == "169.254.169.254" else "93.184.216.34"
        return [(2, 1, 6, "", (ip, port))]
    with pytest.raises(urlsafe.UnsafeURL):
        urlsafe.safe_get("https://example.com/job", client_for(handler), resolver)


def test_follows_safe_redirect():
    def handler(req):
        if req.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, text="hello")
    r = urlsafe.safe_get("https://example.com/old", client_for(handler), public_resolver)
    assert r.status == 200 and r.text == "hello" and r.url.endswith("/new")


def test_redirect_loop_stops():
    def handler(req):
        return httpx.Response(302, headers={"location": "/again"})
    with pytest.raises(urlsafe.FetchError):
        urlsafe.safe_get("https://example.com/x", client_for(handler), public_resolver)


def test_response_size_capped(monkeypatch):
    monkeypatch.setattr(urlsafe, "MAX_BYTES", 100)
    r = urlsafe.safe_get("https://example.com/x",
                         client_for(lambda req: httpx.Response(200, text="a" * 1000)), public_resolver)
    assert r.truncated and len(r.text) == 100


# ---------- html -> text
def test_html_to_text():
    text, title = html_to_text(
        "<html><head><title>Job</title><style>x{}</style></head>"
        "<body><script>evil()</script><h1>Role</h1><ul><li>Python</li><li>SQL</li></ul></body></html>")
    assert title == "Job" and "evil" not in text and "- Python" in text and "- SQL" in text


# ---------- verification
def test_greenhouse_live():
    c = client_for(lambda req: httpx.Response(200, json=GH_JSON))
    v = jobs.verify(GH_URL, c, public_resolver, NOW)
    assert v.status == "live" and v.title == "Backend Engineer"
    assert v.company == "Fictionalco" and v.location == "Remote, US"
    assert "Python and SQL" in v.jd_text and v.posted_age_days == 5


def test_greenhouse_closed_on_404():
    v = jobs.verify(GH_URL, client_for(lambda r: httpx.Response(404)), public_resolver, NOW)
    assert v.status == "closed"


def test_lever_live_and_age():
    v = jobs.verify(LEVER_URL, client_for(lambda r: httpx.Response(200, json=LEVER_JSON)),
                    public_resolver, NOW)
    assert v.status == "live" and v.posted_age_days == 100 and "Excel" in v.jd_text


def test_api_5xx_is_error_not_closed():
    v = jobs.verify(LEVER_URL, client_for(lambda r: httpx.Response(503)), public_resolver, NOW)
    assert v.status == "error"


def test_api_garbage_is_unconfirmed():
    v = jobs.verify(GH_URL, client_for(lambda r: httpx.Response(200, text="<html>oops</html>")),
                    public_resolver, NOW)
    assert v.status == "unconfirmed"


def test_generic_page_states():
    page = lambda body, code=200: client_for(lambda r: httpx.Response(code, text=body))
    u = "https://example.com/careers/1"
    assert jobs.verify(u, page("", 404), public_resolver, NOW).status == "closed"
    assert jobs.verify(u, page("<p>Sorry, this position has been filled.</p>"),
                       public_resolver, NOW).status == "closed"
    v = jobs.verify(u, page("<title>Engineer</title><p>" + "We build things. " * 30 + "</p>"),
                    public_resolver, NOW)
    assert v.status == "unconfirmed" and v.title == "Engineer" and not v.warnings
    short = jobs.verify(u, page("<p>Hi</p>"), public_resolver, NOW)
    assert short.warnings


def test_workday_is_never_marked_live():
    v = jobs.verify("https://acme.wd5.myworkdayjobs.com/site/job/x",
                    client_for(lambda r: httpx.Response(200, text="<p>" + "x " * 200 + "</p>")),
                    public_resolver, NOW)
    assert v.status == "unconfirmed" and "Workday" in v.reason


def test_network_failure_is_error():
    def boom(req):
        raise httpx.ConnectError("down")
    assert jobs.verify(GH_URL, client_for(boom), public_resolver, NOW).status == "error"


# ---------- store, purge, reverify
def make_v(url, status, **kw):
    return jobs.Verification(url=url, portal="other", status=status, reason="t", **kw)


def test_purge_closed_and_stale_keeps_fresh():
    s = jobs_store.JobStore()
    s.save(make_v("u-fresh", "live", title="A"), NOW)
    s.save(make_v("u-closed", "closed"), NOW)
    s.save(make_v("u-stale", "live"), NOW - timedelta(hours=30))
    s.save(make_v("u-erroring-new", "error"), NOW - timedelta(hours=2))
    s.save(make_v("u-erroring-old", "error"), NOW - timedelta(hours=30))
    removed = set(s.purge(NOW))
    assert removed == {"u-closed", "u-stale", "u-erroring-old"}
    assert {r["url"] for r in s.list()} == {"u-fresh", "u-erroring-new"}


def test_error_keeps_old_text_and_counts_failures():
    s = jobs_store.JobStore()
    s.save(make_v("u", "live", title="Keep me", jd_text="body"), NOW)
    s.save(make_v("u", "error"), NOW + timedelta(hours=1))
    row = s.list()[0]
    assert row["title"] == "Keep me" and row["fail_count"] == 1 and row["status"] == "error"


def test_reverify_marks_closed_then_purges():
    s = jobs_store.JobStore()
    s.save(make_v(GH_URL, "live", title="X"), NOW - timedelta(hours=1))
    out = s.reverify_all(lambda u: jobs.verify(u, client_for(lambda r: httpx.Response(404)),
                                               public_resolver, NOW), NOW)
    assert out["closed"] == 1 and out["purged"] == [GH_URL] and s.list() == []


# ---------- API
@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(urlsafe, "RESOLVER", public_resolver)
    monkeypatch.setattr(routes_jobs, "make_client",
                        lambda: client_for(lambda r: httpx.Response(200, json=GH_JSON)))
    routes_jobs.set_store(jobs_store.JobStore())
    return TestClient(app)


def test_ingest_paste(api):
    r = api.post("/api/jobs/ingest", json={"text": "Requirements\nPython, AWS\n3+ years"}).json()
    assert r["source"] == "paste" and r["verification"] is None
    assert r["jd"]["required"] == ["aws", "python"] and r["jd"]["years"] == 3
    assert r["warnings"]


def test_ingest_url_live_and_listed(api):
    r = api.post("/api/jobs/ingest", json={"url": GH_URL}).json()
    assert r["verification"]["status"] == "live" and r["title"] == "Backend Engineer"
    assert "python" in r["jd"]["required"] and r["staffing"]["level"] == "unlikely"
    assert len(api.get("/api/jobs?live_only=true").json()) == 1


def test_ingest_rejects_private_url(api):
    assert api.post("/api/jobs/ingest", json={"url": "http://169.254.169.254/"}).status_code == 400


def test_ingest_requires_input(api):
    assert api.post("/api/jobs/ingest", json={}).status_code == 400


def test_hide_staffing_filter(api):
    store = routes_jobs.get_store()
    store.save(make_v("u1", "live", company="Brightpath Staffing Solutions",
                      jd_text="W2 only. Our client is a bank."))
    store.save(make_v("u2", "live", company="Fabrikam Software", jd_text="Direct hire, permanent role."))
    assert len(api.get("/api/jobs").json()) == 2
    # strong staffing name alone = 'possible', so strict mode is needed to hide it
    kept = api.get("/api/jobs?hide_staffing=true&strict=true").json()
    assert [j["url"] for j in kept] == ["u2"]
    kept = api.get("/api/jobs?direct_hire_only=true").json()
    assert [j["url"] for j in kept] == ["u2"]
