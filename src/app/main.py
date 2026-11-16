from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import latex, llm

app = FastAPI(title="ATS + Sponsorship Career Platform")
STATIC = Path(__file__).parent / "static"


class CompileReq(BaseModel):
    source: str


class RewriteReq(BaseModel):
    bullet: str
    job_description: str = ""


@app.get("/health")
def health():
    return {"ok": True, "model": llm.MODEL}


@app.post("/api/compile")
def compile_tex(req: CompileReq):
    try:
        return Response(latex.compile_pdf(req.source), media_type="application/pdf")
    except latex.LatexError as e:
        raise HTTPException(400, str(e))


@app.post("/api/rewrite")
async def rewrite(req: RewriteReq):
    # TODO: add evidence check (anti-fabrication) before returning
    system = ("You rewrite resume bullets for ATS keyword fit. Never add facts, "
              "employers, degrees, tools or numbers not present in the input bullet.")
    prompt = f"Job description:\n{req.job_description}\n\nBullet:\n{req.bullet}\n\nRewritten bullet:"
    return {"rewritten": await llm.generate(prompt, system)}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
