#!/usr/bin/env python3
"""Build the sponsor database, or inspect a file's headers first.

  python scripts/build_sponsor_data.py --inspect data/raw/LCA_Disclosure_Data_FY2026_Q3.xlsx
  python scripts/build_sponsor_data.py \
      --uscis 2023=data/raw/h1b_datahubexport-2023.csv 2024=data/raw/h1b_datahubexport-2024.csv \
      --lca 2026=data/raw/LCA_Disclosure_Data_FY2026_Q3.xlsx \
      --aliases data/aliases.json --out data/processed/sponsors.db
A bare path (no FY=) for --uscis uses the file's own 'Fiscal Year' column."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.app import sponsor_data, tabular  # noqa: E402


def parse(items, need_fy):
    out = []
    for it in items:
        if "=" in it:
            fy, path = it.split("=", 1)
            out.append((int(fy), path))
        elif need_fy:
            sys.exit(f"--lca needs FY=path (got '{it}')")
        else:
            out.append((None, it))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect")
    ap.add_argument("--uscis", nargs="*", default=[])
    ap.add_argument("--lca", nargs="*", default=[])
    ap.add_argument("--aliases")
    ap.add_argument("--out", default="data/processed/sponsors.db")
    a = ap.parse_args()
    if a.inspect:
        print("\n".join(tabular.headers(a.inspect)))
        return
    aliases = json.load(open(a.aliases)) if a.aliases and Path(a.aliases).exists() else {}
    try:
        summary = sponsor_data.build(a.out, parse(a.uscis, False), parse(a.lca, True), aliases)
    except sponsor_data.DataError as e:
        sys.exit(f"ERROR: {e}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
