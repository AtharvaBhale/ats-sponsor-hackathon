"""Tailor a LaTeX resume to a job: gap analysis + guarded bullet rewrites."""
import re

from . import gap, guard, keywords as kw, latex_resume as lr, llm
from .skills import extract_skills

SYSTEM = ("You rewrite ONE resume bullet for ATS keyword fit. Use only facts in the input "
          "bullet. Never add employers, degrees, certifications, tools or numbers. Keep it one "
          "line, start with a strong past-tense verb. Output only the bullet.")


def clean(out: str) -> str:
    line = next((l for l in out.strip().splitlines() if l.strip()), "")
    line = re.sub(r"^(rewritten bullet:|bullet:)\s*", "", line.strip(), flags=re.I)
    return line.lstrip("-*• ").strip().strip('"').strip()


async def default_rewrite(bullet: str, allowed: list) -> str:
    prompt = (f"Keywords you may emphasize if truthful: {', '.join(allowed) or 'none'}\n"
              f"Bullet:\n{bullet}\n\nRewritten bullet:")
    return clean(await llm.generate(prompt, SYSTEM, 120))


async def tailor(resume_tex: str, jd: str, additions: list | None = None,
                 rewrite_fn=default_rewrite, max_bullets: int = 30) -> dict:
    additions = [a.strip() for a in (additions or []) if a.strip()]
    evidence = lr.latex_to_text(lr.body_text(resume_tex)) + "\n" + "\n".join(additions)
    analysis = gap.analyze(evidence, jd)
    match = kw.fit(jd, evidence)
    allowed_stems = set(match["matched_stems"])
    allowed = match["matched"][:12]
    bullets = lr.extract_bullets(resume_tex)[:max_bullets]
    accepted, results, skipped = {}, [], None
    if not allowed_stems:
        skipped = ("None of this job's key terms appear in your resume, so there is nothing "
                   "truthful to add. No bullets were changed.")
    for i, (_, _, raw) in enumerate(bullets):
        original = lr.latex_to_text(raw, collapse=True)
        row = {"index": i, "original": original, "rewritten": original, "accepted": False,
               "violations": [], "note": "", "gained": []}
        results.append(row)
        if skipped:
            continue
        cand = await rewrite_fn(original, allowed)
        if not cand:
            row["violations"] = ["empty rewrite"]
        elif len(cand) > 2.2 * len(original) + 20:
            row["violations"] = ["rewrite is much longer than the original"]
        else:
            row["violations"] = guard.check(cand, evidence).violations
        if not row["violations"]:
            lost = guard.facts(original) - guard.facts(cand)
            if lost:
                row["violations"] = ["drops from the original: " + ", ".join(sorted(lost))]
        if row["violations"]:
            continue
        added = kw.gained(original, cand, allowed_stems)
        if cand == original:
            row["note"] = "Model returned the bullet unchanged. Original kept."
        elif not added:
            row["note"] = "No new job keyword added, so the original was kept."
        else:
            row.update(accepted=True, rewritten=cand, gained=added)
            accepted[i] = cand
    return {"tex": lr.replace_bullets(resume_tex, accepted), "gap": analysis, "fit": match,
            "bullets": results,
            "summary": {"bullets": len(results), "accepted": len(accepted),
                        "rejected": sum(1 for r in results if r["violations"]),
                        "keywords_allowed": allowed, "skipped_reason": skipped}}
