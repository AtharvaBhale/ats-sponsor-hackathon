import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from . import docs_parse, guard, latex, latex_resume, llm, resume_build, tailor as tailor_mod

router = APIRouter(prefix="/api", tags=["documents"])
draft_fn = None  # tests replace this: async (evidence, skill) -> str

SYS = ("Write ONE resume bullet (one line, strong past-tense verb) using ONLY the facts in the "
       "evidence. Never add employers, tools, numbers, degrees or certifications not in it. "
       "Output only the bullet.")


async def _read(file: UploadFile):
    try:
        return docs_parse.extract_text(file.filename, await file.read())
    except docs_parse.ParseError as e:
        raise HTTPException(400, str(e))


@router.post("/resume/upload")
async def resume_upload(file: UploadFile = File(...)):
    text, warnings = await _read(file)
    is_tex = (file.filename or "").lower().endswith(".tex")
    return {"filename": file.filename, "text": text, "warnings": warnings,
            "latex": text if is_tex else resume_build.text_to_latex(text)}


@router.post("/evidence/upload")
async def evidence_upload(file: UploadFile = File(...), job_description: str = Form("")):
    text, warnings = await _read(file)
    return {**docs_parse.screen_evidence(text, job_description), "warnings": warnings}


class SynthReq(BaseModel):
    evidence: str
    skill: str = ""


@router.post("/synthesize")
async def synthesize(req: SynthReq):
    if len(req.evidence.strip()) < 15:
        raise HTTPException(400, "Describe the project, coursework or experience first")
    try:
        if draft_fn:
            bullet = await draft_fn(req.evidence, req.skill)
        else:
            raw = await llm.generate(f"Evidence:\n{req.evidence}\n\nBullet:", SYS, 100)
            bullet = tailor_mod.clean(raw)
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Local LLM unavailable (is Ollama running?): {e}")
    check = guard.check(bullet, req.evidence) if bullet else None
    return {"bullet": bullet, "accepted": bool(bullet) and check.ok,
            "violations": check.violations if check else ["empty draft"]}


class AddReq(BaseModel):
    tex: str
    bullet: str
    section: str = "Projects"


@router.post("/resume/add-bullet")
def add_bullet(req: AddReq):
    return {"tex": latex_resume.insert_bullet(req.tex, req.bullet, req.section)}


class ExportReq(BaseModel):
    tex: str
    format: str = "txt"


@router.post("/export")
def export(req: ExportReq):
    f = req.format.lower()
    if f == "pdf":
        try:
            data, mt = latex.compile_pdf(req.tex), "application/pdf"
        except latex.LatexError as e:
            raise HTTPException(400, str(e))
    elif f in ("txt", "md"):
        data, mt = resume_build.tex_to_plain(req.tex, f == "md").encode(), "text/plain; charset=utf-8"
    elif f == "tex":
        data, mt = req.tex.encode(), "text/plain; charset=utf-8"
    else:
        raise HTTPException(400, "format must be txt, md, pdf or tex")
    return Response(data, media_type=mt, headers={"Content-Disposition": f'attachment; filename="resume.{f}"'})
