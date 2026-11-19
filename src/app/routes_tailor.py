import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import tailor as tailor_mod

router = APIRouter(prefix="/api", tags=["tailor"])
rewrite_fn = tailor_mod.default_rewrite  # tests replace this


class TailorReq(BaseModel):
    resume_latex: str
    job_description: str
    additions: list[str] = []  # user answers to gap questions: evidence the user vouches for


@router.post("/tailor")
async def tailor(req: TailorReq):
    if not req.resume_latex.strip() or not req.job_description.strip():
        raise HTTPException(400, "Provide both a LaTeX resume and a job description")
    try:
        return await tailor_mod.tailor(req.resume_latex, req.job_description, req.additions, rewrite_fn)
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Local LLM unavailable (is Ollama running?): {e}")
