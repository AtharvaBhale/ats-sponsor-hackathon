# Data sources and how to rebuild the sponsor database

All data is public U.S. government data. No personal data is used.

## 1. Download (do this in a normal browser; DOL files may be bot-gated)

**USCIS H-1B Employer Data Hub files** (CSV, one per fiscal year, ~10 MB each)
- Landing: https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
- Older years: https://www.uscis.gov/archive/h-1b-employer-data-hub-files
- Get the 4 most recent fiscal years available. Save as `data/raw/h1b_datahubexport-YYYY.csv`.

**DOL OFLC LCA disclosure data** (XLSX, cumulative per fiscal year, 50-150 MB each)
- Page: https://www.dol.gov/agencies/eta/foreign-labor/performance (LCA Programs section)
- Get the NEWEST cumulative file for the current FY (e.g. FY2026 Q3) and, if available, the
  full-year file for the previous FY. Do NOT download every quarter of the same year; each file
  already contains the earlier quarters.
- The same page links the record layout (column dictionary).
- Save under `data/raw/` (this folder is git-ignored).

## 2. Check the headers before building (30 seconds, avoids silent errors)
    python scripts/build_sponsor_data.py --inspect data/raw/<the LCA file>.xlsx
    python scripts/build_sponsor_data.py --inspect data/raw/h1b_datahubexport-2024.csv
The build fails loudly, listing the real headers, if an essential column is not found.

## 3. Build
    python scripts/build_sponsor_data.py \
      --uscis data/raw/h1b_datahubexport-2022.csv data/raw/h1b_datahubexport-2023.csv \
      --lca 2025=data/raw/<FY2025 file>.xlsx 2026=data/raw/<FY2026 file>.xlsx \
      --aliases data/aliases.json --out data/processed/sponsors.db
A bare path for `--uscis` uses the file's own "Fiscal Year" column; `FY=path` overrides it.
Reading a 100 MB XLSX takes minutes. Read the printed `warnings` list.

## 4. Optional curated files
- `data/aliases.json`: `{"Job Board Name": "Legal Filing Name"}`, e.g. when postings say "Acme" and
  filings say "Acme Cloud Services LLC". The tier output lists "similar filer names" to help.
- `data/opt_friendly.txt`: one company name per line, curated by you (no public bulk source exists).

## 5. Commit policy
Commit `data/processed/sponsors.db` only if it is under ~50 MB. Never commit `data/raw/`.

## Known limits
- Matching is by normalized company name; parents/subsidiaries/renames can be missed.
- USCIS data lags the LCA data by a year or more; "recently active" uses LCA certifications.
- LCA certification shows intent to hire, not an approved petition or a granted visa.
