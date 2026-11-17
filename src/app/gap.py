"""Resume vs JD gap analysis. Produces questions to ask the user, never invents content."""
from .skills import extract_skills, parse_jd


def analyze(resume_text: str, jd_text: str) -> dict:
    jd = parse_jd(jd_text)
    have = extract_skills(resume_text)
    matched_req = sorted(jd["required"] & have)
    missing_req = sorted(jd["required"] - have)
    matched_pref = sorted(jd["preferred"] & have)
    missing_pref = sorted(jd["preferred"] - have)
    total = len(jd["required"])
    coverage = round(len(matched_req) / total, 2) if total else None
    questions = [
        f"The job asks for {s}. Do you have a project, coursework, certification or "
        f"experience with it? Add details, or skip if you don't."
        for s in missing_req
    ]
    return {
        "matched_required": matched_req, "missing_required": missing_req,
        "matched_preferred": matched_pref, "missing_preferred": missing_pref,
        "required_coverage": coverage, "years_requested": jd["years"],
        "questions": questions,
    }
