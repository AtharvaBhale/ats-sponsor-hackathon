# Architecture Overview

## Final tech stack
Python + FastAPI + uvicorn; SQLite; httpx; pypdf, python-docx, openpyxl; Ollama with
`qwen2.5:1.5b`; pdflatex (tectonic if present); a single static HTML/JS page. No frontend build.

## How a request flows
    browser page ──► FastAPI ──► tailor ──► Ollama (local LLM)
                        │            └──► guard (deterministic checks)  ◄── evidence: resume body + user answers
                        ├──► jobs ──► Greenhouse / Lever public APIs (via SSRF-safe fetch) ──► SQLite (24h purge)
                        ├──► sponsorship ──► sponsors.db (built from USCIS CSVs)
                        ├──► staffing (name, NAICS, LCA patterns, posting language)
                        └──► latex ──► pdflatex/tectonic ──► PDF

## Folder structure
    src/app/
      main.py, routes_*.py   API wiring
      latex.py               compile with timeout, blocklist, no shell-escape
      latex_resume.py        find/replace bullets (\item and custom macros like \resumeItem)
      tailor.py, guard.py    tailoring pipeline and anti-fabrication rules
      keywords.py, skills.py, gap.py   job/resume fit, skill extraction, gap questions
      docs_parse.py, resume_build.py   uploads, text->LaTeX, LaTeX->txt/md
      jobs.py, jobs_store.py, urlsafe.py, htmltext.py   verification, store, SSRF-safe fetch
      staffing.py, sponsorship.py, sponsor_data.py, names.py, tabular.py   employer analysis
      llm.py                 Ollama client
      static/index.html      the UI
    scripts/   setup.sh, start_ollama.sh, build_sponsor_data.py, check_tier.py
    data/      aliases.json, processed/sponsors.db (raw files are git-ignored)
    tests/     automated tests (154)

## Truthfulness design (the core requirement)
The model never decides what is true. For every bullet:
1. **Evidence** = the resume body + facts the user typed or uploaded. Nothing else counts.
2. The model may only emphasise **keywords that are in both the job and the evidence**.
3. `guard.check` rejects a rewrite containing any new number, tool/skill, degree, certification
   or proper noun not in the evidence.
4. A rewrite that **drops** a skill or number from the original is rejected.
5. A rewrite that adds **no truthful job keyword** is rejected (this removed pointless edits).
6. On any rejection the **original text is kept** and the reason is shown.
7. If no job keyword is supported by the resume, the model is not called at all.

## Gap synthesis
Domain-independent keyword fit (strong / partial / weak), tech-skill gap list with one question
per missing required skill, and user answers become evidence. Transcripts/certificates are parsed
(PDF, DOCX, TXT), lines are kept only if relevant to the job, and personal identifiers (SSN-like
numbers, student IDs, dates of birth, passport mentions) are dropped. A bullet can be drafted from
the user's own text and is checked by the same guard.

## Job verification (anti-ghost)
Statuses: `live` (confirmed by the portal API), `closed` (404 or "no longer available"),
`unconfirmed` (page reachable but no portal API, including Workday), `error` (network/5xx;
never treated as closed). Stored in SQLite; closed postings and any posting not confirmed for
24 hours are purged (`/api/jobs/reverify`, hourly background job available). Postings older
than 60 days get a ghost-job warning. All fetches are SSRF-safe: http(s) only, ports 80/443,
every resolved IP must be public, redirects re-validated, size capped.

## Sponsorship tiers
Window = latest 4 fiscal years present. **Proven**: approvals in >=3 years, >=10 initial
approvals, >=90% approval rate (plus recent LCA certifications when DOL data is loaded).
**Emerging**: some H-1B evidence below those bars. **OPT-Only**: no H-1B evidence but the
posting mentions OPT/CPT/F-1 or the company is on a curated list. **Non-Sponsor**: no evidence.
**Unknown**: no database, or no exact match but similar filer names exist (shown to the user).
A posting that says it does not sponsor sets `effective_tier` for that role only.

## Staffing detection
Additive, explainable score from: name terms, NAICS (5613xx), DOL LCA patterns (secondary
entity share, out-of-state worksites, H-1B dependent), and posting language (W2 only, C2C,
"our client", bench...). Output is an advisory badge, never a verdict.

## Codespaces
`.devcontainer/devcontainer.json` + `scripts/setup.sh` (reports OK/FAIL per step) install
Ollama, pull the model, and install LaTeX; `start_ollama.sh` restarts the model server.
Measured in a Codespace: qwen2.5:1.5b **13.8 tokens/s** on CPU; LaTeX compile **0.12 s** through
the API (0.26 s from the CLI); live Greenhouse verification works from the Codespace.

## Privacy
Resume text goes only to the local model and the local LaTeX engine. The only outbound
requests are job-portal lookups for URLs the user supplies. No analytics, no third-party AI.

## What changed from the plan
- Planned tectonic only; the install failed in the Codespace, so a pdflatex fallback was added.
- Planned a simple "accept if the guard passes" rule; real testing showed that accepted
  harmless-but-worse edits, so the keyword-gain and fact-preservation rules were added.
- Planned DOL LCA data for staffing patterns and recency; only the USCIS data was loaded in time.
- Planned a map, wage estimator, chat refinement and HR two-factor: not built.
