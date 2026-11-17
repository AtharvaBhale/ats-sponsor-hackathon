from fastapi import APIRouter
from pydantic import BaseModel

from . import staffing

router = APIRouter(prefix="/api/staffing", tags=["staffing"])


class LcaIn(BaseModel):
    n: int = 0
    secondary_ratio: float | None = None
    mismatch_ratio: float | None = None
    h1b_dependent: bool = False


class AssessReq(BaseModel):
    name: str
    naics: str | None = None
    postings: list[str] = []
    lca: LcaIn | None = None


@router.post("/assess")
def assess(req: AssessReq):
    lca = staffing.LcaStats(**req.lca.model_dump()) if req.lca else None
    return staffing.assess(req.name, req.naics, lca, req.postings).to_dict()
