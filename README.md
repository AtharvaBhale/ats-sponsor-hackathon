# ATS Resume Tailor + Job Verification + Sponsorship Platform

**Live URL:** <!-- FILL: public Codespaces port URL (only works while the Codespace is running) -->
**Walkthrough video:** see [`docs/walkthrough.md`](docs/walkthrough.md)

A privacy-first career tool that runs on a **local open-source LLM** (Qwen2.5 1.5B via Ollama).
Your resume never leaves the machine. It tailors a LaTeX resume to a job description **without
inventing anything**, verifies that a job posting is still open, scores the employer's H-1B
sponsorship history, and flags staffing intermediaries.

## What it does
| Area | Features |
|---|---|
| **Resume editor** | Overleaf-style LaTeX editor with live PDF preview. Upload PDF/DOCX/TXT/TEX. Export PDF, plain text, Markdown, LaTeX. |
| **Tailoring** | Local LLM rewrites each bullet. A deterministic guard blocks any invented number, tool, degree, certification or employer, and any rewrite that drops a fact from the original or adds no truthful job keyword. |
| **Gap analysis** | Keyword-match score for any field, required-skill gaps, a targeted question per gap, and transcript/certificate upload screened for relevance (personal IDs dropped). Drafts a bullet from *your* evidence, guard-checked. |
| **Anti-ghost verification** | Greenhouse and Lever postings confirmed via their public portal APIs; closed or stale postings purged within 24 hours; SSRF-safe URL fetching. |
| **Sponsorship tiers** | Proven / Emerging / OPT-Only / Non-Sponsor (+ Unknown) from USCIS H-1B Employer Data Hub records. |
| **Staffing detection** | Advisory badge for likely staffing intermediaries; filters to hide them or require direct hire. |

## Run in GitHub Codespaces (the supported way)
1. Open the repo in a Codespace. `scripts/setup.sh` installs Ollama, the model, and LaTeX
   (read its `=== SUMMARY ===` block; re-run any time with `make setup`).
2. `make run`, then open forwarded port **8000**.
3. `make test` runs the automated tests. `make` lists every command.

## Run locally
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    make test
    make run          # needs Ollama + a LaTeX engine for tailoring and PDF preview

## Sponsor data
`data/processed/sponsors.db` is built from public USCIS CSVs (see `docs/data_sources.md`).
Raw files are not committed. Rebuild:
    python scripts/build_sponsor_data.py --uscis data/raw/*.csv --aliases data/aliases.json --out data/processed/sponsors.db
    python scripts/check_tier.py "Google" "Microsoft"

## Documentation
- [`planning/planning.md`](planning/planning.md): scope, plan, cut list
- [`docs/architecture.md`](docs/architecture.md): design and how each requirement is met
- [`docs/test_cases.md`](docs/test_cases.md): test results, including real-API runs
- [`docs/reflection.md`](docs/reflection.md): what worked, what broke, known limitations, AI usage
- [`docs/data_sources.md`](docs/data_sources.md), [`docs/COMMANDS.md`](docs/COMMANDS.md)

## Data and privacy
Only synthetic or fictional resumes are used in tests and demos. Public government data
(USCIS) is the only external dataset. No resume text is sent to any third party.
