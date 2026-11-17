import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import jobs, jobs_store, staffing, urlsafe
from .skills import parse_jd

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
_STORE: jobs_store.JobStore | None = None


def make_client() -> httpx.Client:
    return httpx.Client(timeout=urlsafe.TIMEOUT, follow_redirects=False)


def get_store() -> jobs_store.JobStore:
    global _STORE
    if _STORE is None:
        path = os.getenv("DB_PATH", "data/jobs.db")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _STORE = jobs_store.JobStore(path)
    return _STORE


def set_store(store: jobs_store.JobStore) -> None:
    global _STORE
    _STORE = store


class IngestReq(BaseModel):
    url: str | None = None
    text: str | None = None


@router.post("/ingest")
def ingest(req: IngestReq):
    if not (req.url or req.text):
        raise HTTPException(400, "Provide a job URL or paste the job description text")
    warnings, verification = [], None
    title = company = location = ""
    jd_text = (req.text or "").strip()

    if req.url:
        client = make_client()
        try:
            v = jobs.verify(req.url.strip(), client)
        except urlsafe.UnsafeURL as e:
            raise HTTPException(400, str(e))
        finally:
            client.close()
        get_store().save(v)
        verification = v.to_dict()
        title, company, location = v.title, v.company, v.location
        warnings += v.warnings
        jd_text = jd_text or v.jd_text
        if v.status == "closed":
            warnings.append("This posting appears to be closed.")
        if v.posted_age_days is not None and v.posted_age_days > 60:
            warnings.append(f"Posting was last updated {v.posted_age_days} days ago "
                            "(older postings are more likely to be ghost jobs).")
    else:
        warnings.append("Pasted description: not verified against a live posting.")

    jd = parse_jd(jd_text)
    assessment = staffing.assess(company or "Unknown", postings=[jd_text] if jd_text else [])
    return {"source": "url" if req.url else "paste", "verification": verification,
            "title": title, "company": company, "location": location, "jd_text": jd_text,
            "jd": {"required": sorted(jd["required"]), "preferred": sorted(jd["preferred"]),
                   "years": jd["years"]},
            "staffing": assessment.to_dict(), "warnings": warnings}


@router.get("")
def list_jobs(live_only: bool = False, hide_staffing: bool = False,
              direct_hire_only: bool = False, strict: bool = False):
    items = []
    for row in get_store().list(live_only):
        a = staffing.assess(row["company"] or "Unknown", postings=[row["jd_text"] or ""])
        row["staffing"] = a.to_dict()
        row.pop("jd_text", None)
        items.append({"row": row, "assessment": a})
    kept = staffing.filter_companies(items, hide_staffing, direct_hire_only, strict)
    return [i["row"] for i in kept]


@router.post("/reverify")
def reverify():
    client = make_client()
    try:
        return get_store().reverify_all(lambda u: jobs.verify(u, client))
    finally:
        client.close()


@router.post("/purge")
def purge():
    return {"purged": get_store().purge()}
