"""Tailor a LaTeX resume to a job: gap analysis + guarded bullet rewrites."""
import re

from . import gap, guard, latex_resume as lr, llm
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
    allowed = sorted(extract_skills(jd) & extract_skills(evidence))
    accepted, results = {}, []
    for i, (_, _, raw) in enumerate(lr.extract_bullets(resume_tex)[:max_bullets]):
        original = lr.latex_to_text(raw, collapse=True)
        cand = await rewrite_fn(original, allowed)
        reasons = []
        if not cand:
            reasons.append("empty rewrite")
        elif len(cand) > 2.2 * len(original) + 20:
            reasons.append("rewrite is much longer than the original")
        if cand and not reasons:
            reasons = guard.check(cand, evidence).violations
        ok = bool(cand) and not reasons and cand != original
        if ok:
            accepted[i] = cand
        results.append({"index": i, "original": original, "rewritten": cand if ok else original,
                        "accepted": ok, "violations": reasons,
                        "unchanged": bool(cand) and not reasons and cand == original})
    return {"tex": lr.replace_bullets(resume_tex, accepted), "gap": analysis, "bullets": results,
            "summary": {"bullets": len(results), "accepted": len(accepted),
                        "rejected": sum(1 for r in results if r["violations"]),
                        "keywords_allowed": allowed}}
