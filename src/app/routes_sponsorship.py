from fastapi import APIRouter
from pydantic import BaseModel

from . import sponsorship

router = APIRouter(prefix="/api/sponsorship", tags=["sponsorship"])


class TierReq(BaseModel):
    company: str
    posting_text: str = ""


@router.post("/tier")
def tier(req: TierReq):
    return sponsorship.tier_for(req.company, req.posting_text)


@router.get("/status")
def status():
    db = sponsorship.get_db()
    return {"loaded": db is not None, "meta": db.meta if db else None}
