# Planning Document

> **Honesty note:** the plan below was agreed in conversation before the first line of code, but
> this file was written into the repo late (during the final days), not at the start. It records
> the plan as it was made, followed by what actually happened in `docs/architecture.md`.

## Tech Stack
**Framework / language:** Python 3.10+ with FastAPI; one static HTML/JS page (no build step).
Chosen because the brief needs a local-LLM service that runs in Codespaces, a solo builder has
days not weeks, and a plain API is easy to test automatically.
**Key libraries:** httpx (portal and Ollama calls), pypdf and python-docx (uploads), openpyxl
(DOL files), SQLite (job store and sponsor data), pytest.
**LLM:** Qwen2.5 1.5B through Ollama, CPU only. Small enough for a 2-core Codespace. All
safety-critical behaviour is **deterministic code around the model**, because a 1.5B model
cannot be trusted to follow "never fabricate".
**LaTeX:** tectonic preferred; pdflatex (TeX Live) fallback, shell-escape disabled.

## Feature areas (instead of detection categories)
| Rubric area | Weight | Planned technique |
|---|---|---|
| ATS optimization + LaTeX editor | 30% | LaTeX editor + live preview; LLM rewrites bullets; deterministic guard |
| Active job verification | 25% | Greenhouse/Lever public APIs, 24h purge, SSRF protection |
| Gap synthesis and evidence | 20% | Skill/keyword extraction, targeted questions, document parsing, relevance screening |
| Codespaces model efficiency | 15% | devcontainer, small model, benchmark |
| Documentation and video | 10% | Written from real run results |
| Tier 1 sponsorship scoring | required | USCIS Employer Data Hub tiers |

## Phases
| Phase | Goals |
|---|---|
| 1 | Repo skeleton, devcontainer, LaTeX compile, Ollama client, spike the three risks (model speed, compile time, real portal APIs) |
| 2 | Gap analysis, anti-fabrication guard, staffing detection |
| 3 | Job input and verification, store, purge, SSRF protection |
| 4 | Sponsorship data pipeline and tiers; UI wiring; uploads and exports |
| 5 | Real-data testing, fixes, docs, video |

## What I'd cut if time is short
First: interactive map, H-1B wage estimator, chat refinement. Then: Workday verification, HR
two-factor protocol, DOL LCA data. Last: never the anti-fabrication guard or job verification.

## Open questions / risks
- A 1.5B model may write weak rewrites (mitigated: only accept rewrites that add a truthful keyword).
- Public URL vs a local LLM: free hosts cannot run the model.
- Employer-name matching between job boards and government filings.
- No public bulk source exists for "OPT-friendly" employers.
