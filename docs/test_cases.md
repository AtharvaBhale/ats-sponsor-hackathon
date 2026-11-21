# Test Cases and Results

Reproduce everything with `make test` (automated) and the commands under each manual case.
All resumes and job descriptions in automated tests are synthetic. Real runs used public job
postings and public USCIS data only.

## A. Resume optimization (synthetic)
| ID | Case | Expected | Result | Evidence |
|---|---|---|---|---|
| R1 | Rewrite adds a truthful job keyword ("inventory REST API") | Accepted, keywords listed | Pass | `test_rewrite_that_adds_a_truthful_keyword_is_accepted` |
| R2 | Cosmetic rewrite (drops "an") | Original kept, no keyword added | Pass | `test_cosmetic_rewrite_is_not_accepted` |
| R3 | Rewrite invents "40%" and "Kubernetes" | Blocked, reasons shown | Pass | `test_fabricated_rewrite_is_blocked` |
| R4 | Rewrite deletes "REST API" and weakens the verb | Blocked: drops a fact | Pass | `test_rewrite_that_drops_a_skill_...` |
| R5 | Rewrite drops a number ("40%") | Blocked | Pass | `test_rewrite_that_drops_a_number_is_blocked` |
| R6 | Job unrelated to the resume (finance job vs software resume) | Weak match, model not called, 0 changes | Pass | `test_unrelated_job_changes_nothing_and_never_calls_the_model` |
| R7 | Resume using a custom `\resumeItem{}` macro, multi-line, nested braces | All bullets found, macro definitions untouched | Pass | `test_macro_bullets_found_in_body_only` |
| R8 | Inflected word ("RESTful" for "REST") | Not a false positive | Pass | `test_inflection_of_evidence_word_is_not_a_new_name` |
| R9 | Invented company next to a real one ("Acmeville" vs "Acme") | Blocked | Pass | `test_invented_company_near_an_evidence_word_still_blocked` |

**Manual (Codespace), to record before submission**
| ID | Steps | Expected | Result |
|---|---|---|---|
| R-M1 positive | Sample resume + a job asking for REST/inventory/testing; click Tailor | Weak-to-strong match; some bullets accepted with "Added keywords" | <!-- FILL: paste result / screenshot docs/evidence/positive.png --> |
| R-M2 negative | Sample resume + a finance/investing job description | Red "Weak match" banner, 0 changes, "nothing truthful to add" | <!-- FILL: screenshot docs/evidence/negative.png --> |

## B. Gap synthesis
| ID | Case | Result | Evidence |
|---|---|---|---|
| G1 | Missing required skill produces a targeted question | Pass | `test_gap_reports_missing_and_additions_become_evidence` |
| G2 | User's own answer becomes evidence and unlocks that skill in rewrites | Pass | `test_user_addition_lets_a_rewrite_use_that_skill` |
| G3 | Uploaded transcript: relevant lines kept; SSN and student ID dropped | Pass | `test_screening_keeps_relevant_drops_pii_and_noise` |
| G4 | PDF, DOCX, TXT parsing; corrupt/unsupported/oversize files rejected; scanned PDF warns | Pass | `test_extract_pdf_docx_txt`, `test_bad_inputs` |
| G5 | Bullet drafted from user evidence passes; one needing facts not provided is blocked | Pass | `test_api_synthesize_guard` |
| G6 | Resume text to LaTeX, and LaTeX to plain text/Markdown | Pass | `test_text_to_latex_...`, `test_tex_to_plain_...` |
| G7 | Skill matcher does not treat "go-to-market", "excel at", "R&D" as skills | Pass | `tests/test_skills.py` (23 cases) |

## C. Anti-ghost job verification
Real runs against public portals (not mocks):
| ID | Input | Expected | Actual |
|---|---|---|---|
| V1 | Live Greenhouse posting | live + title + JD text | `live`, "Enterprise Account Executive", 5,049 characters (run on Mac and in Codespace) |
| V2 | Live Lever posting | live | `live`, "Customer Success Manager", 6,733 characters |
| V3 | Removed Greenhouse posting | closed, then purged | `closed`; `/api/jobs/purge` returned that URL; list no longer showed it |
| V4 | `http://169.254.169.254/...` (cloud metadata address) | blocked | `HTTP/1.1 400 Bad Request` |

Automated (mocked HTTP): API 404 = closed; 5xx = error not closed; garbage 200 = unconfirmed;
Workday never `live`; closed-phrase detection; redirect to a private IP blocked; hostname
resolving to a private IP blocked; response size cap; 24-hour purge of closed/stale items while
keeping fresh ones (`tests/test_jobs.py`, 35+ cases).

## D. Sponsorship and staffing
Real USCIS data: 154,112 rows -> 84,683 employers, FY2021-2023, no warnings.
| ID | Company | Result |
|---|---|---|
| S1 | Google | Proven: 3,071 initial approvals, 98.9% approval rate, 3 years active |
| S2 | Microsoft | Proven: 2,290 initial approvals, 98.9% |
| S3 | Amazon | Unknown (low confidence): no exact name; lists 5 similar filers |
| S4 | Cognizant | Unknown: no exact name; lists similar filers |
| S5 | Walmart | Unknown: only "WALMART ASSOCIATES INC" found; alias needed |
Unknown is the designed behaviour when a company files under longer legal names. Aliases in
`data/aliases.json` resolve them. Automated tests cover every tier and the staffing score
(`tests/test_sponsorship.py`, `tests/test_staffing.py`).

## E. Environment measurements (Codespace, 2 cores, CPU only)
| Measure | Value |
|---|---|
| Model | qwen2.5:1.5b (986 MB), 13.8 tokens/s |
| LaTeX compile | 0.12 s via the API, 0.26 s from the CLI |
| Tailor, 2 bullets | 5.0 s; first model call after idle ~10 s (cold load) |
| Tests | 154 automated tests <!-- FILL: confirm count after running make test in the Codespace --> |

## F. Defects found by testing (and fixed)
1. Plain-`pytest` could not import the package: added `pytest.ini`.
2. `setup.sh` could not install tectonic in the Codespace: added reporting per step and a pdflatex fallback.
3. The skill matcher flagged "go" from "go-to-market" in a real sales posting: strict patterns for ambiguous words.
4. The guard rejected "RESTful" for evidence saying "REST": inflection and skill-aware check.
5. An accepted rewrite deleted "REST API" and weakened the claim (seen in the UI on an unrelated job): added fact-preservation, keyword-gain, and fit-based skipping.
6. A real LaTeX resume using `\resumeItem{}` produced zero bullets: custom bullet macros are now detected.
7. The OPT detector silently never worked (variable name collision): caught by a test.
8. An employer filing under a longer legal name was labelled Non-Sponsor: now Unknown with candidates shown.
