# Reflection

## What I built
A local-LLM resume tailor with an Overleaf-style LaTeX editor, a deterministic anti-fabrication
guard, gap analysis with evidence upload, Greenhouse/Lever job verification with 24-hour purge,
USCIS-based sponsorship tiers, and staffing-intermediary flags, running in Codespaces.

**Works reliably:** LaTeX editing and PDF preview; guarded tailoring (including a resume with
custom bullet macros); gap questions; document parsing; real Greenhouse and Lever verification;
SSRF protection; sponsorship tiers on real USCIS data for exact-name employers; exports.

**Works with caveats:** tailoring quality is limited by a 1.5B model, so many bullets stay
unchanged (by design: a rewrite must add a truthful keyword). Sponsorship tiers are Unknown for
big employers filing under several legal names unless an alias is added.

## Known limitations
- Scanned PDFs are not read (no OCR).
- Rewrites operate on plain text, so inline formatting inside a bullet is lost when it is replaced.
- Evidence is resume-wide: a keyword from one job could be reused in an unrelated bullet.
  The guard prevents invented facts but not mixing real ones; it also cannot detect a weaker verb.
- Skill-by-skill gaps use a ~70-term tech vocabulary; the keyword-fit score is domain independent.
- Workday postings are never marked live. HR two-factor confirmation is not built.
- Sponsor data covers FY2021-2023 only (USCIS publishes with a delay). DOL LCA ingestion is
  implemented and tested on synthetic data but was **not run on a real DOL file**, so the
  LCA-based staffing patterns and "recently active" check are unproven on real data.
- OPT-Only has no public bulk data source; it relies on posting text and a curated list.
- Tier thresholds are my own judgement and have not been validated beyond a few known companies.
- The live URL is a Codespaces port, which only works while the Codespace is running.
- Not built: state map, wage estimator, chat refinement.

## What I would do differently / next
Load a real DOL LCA file; auto-aggregate related filer names with clear labelling; try a 3B
model and few-shot prompts; per-bullet evidence scoping; a section picker for drafted bullets;
Workday support; a deployed fallback without the LLM.

## AI tools used
- **Claude (Anthropic)** as a pair-programming assistant: it wrote most of the code and tests
  from my requirements. I ran everything in my own environment and Codespaces, reported real
  failures with screenshots and logs, and the fixes came from those results (see section F of
  `docs/test_cases.md`). Several of Claude's early assumptions were wrong (for example a
  failing Lever test URL, a skill-matcher false positive on a real posting) and were caught
  only by running against real data.
- **Qwen2.5 1.5B via Ollama** is the product's local model: it rewrites bullets and drafts
  bullets from user evidence. It is never trusted for safety; deterministic code decides what is
  accepted.
- Why local AI: resumes are sensitive; nothing is sent to a third-party AI service.
