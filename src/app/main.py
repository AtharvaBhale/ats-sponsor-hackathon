from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import gap, guard, latex, llm
from .skills import extract_skills

from .routes_staffing import router as staffing_router
app.include_router(staffing_router)   # place right after app = FastAPI(...)

app = FastAPI(title="ATS + Sponsorship Career Platform")
STATIC = Path(__file__).parent / "static"


class CompileReq(BaseModel):
    source: str


class RewriteReq(BaseModel):
    bullet: str
    job_description: str = ""
    evidence: str = ""  # original resume text + user-confirmed additions + parsed uploads


class AnalyzeReq(BaseModel):
    resume_text: str
    job_description: str


@app.get("/health")
def health():
    return {"ok": True, "model": llm.MODEL}


@app.post("/api/compile")
def compile_tex(req: CompileReq):
    try:
        return Response(latex.compile_pdf(req.source), media_type="application/pdf")
    except latex.LatexError as e:
        raise HTTPException(400, str(e))


@app.post("/api/analyze")
def analyze(req: AnalyzeReq):
    return gap.analyze(req.resume_text, req.job_description)


@app.post("/api/rewrite")
async def rewrite(req: RewriteReq):
    evidence = req.evidence or req.bullet
    # Only keywords the candidate already has evidence for may be used in the rewrite.
    allowed = sorted(extract_skills(req.job_description) & extract_skills(evidence))
    system = ("You rewrite one resume bullet for ATS keyword fit. Use only facts in the input "
              "bullet. Never add employers, degrees, certifications, tools or numbers.")
    prompt = (f"Keywords you may emphasize if truthful: {', '.join(allowed) or 'none'}\n"
              f"Bullet:\n{req.bullet}\n\nRewritten bullet:")
    candidate = await llm.generate(prompt, system)
    result = guard.check(candidate, evidence)
    return {
        "original": req.bullet,
        "rewritten": candidate if result.ok else req.bullet,  # fall back to the truth
        "accepted": result.ok,
        "violations": result.violations,
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
