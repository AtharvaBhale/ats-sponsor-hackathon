#!/usr/bin/env python3
"""Print the sponsorship tier for company names.
   python scripts/check_tier.py "Some Company" "Another Company"
Uses data/processed/sponsors.db (override with the SPONSOR_DB environment variable)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.app import sponsorship  # noqa: E402


def main():
    db = sponsorship.get_db()
    if db is None:
        sys.exit("No sponsor database found. Run scripts/build_sponsor_data.py first.")
    print("data:", db.meta)
    for name in sys.argv[1:]:
        r = sponsorship.classify(db, name)
        print(f"\n{name}: {r['tier']} ({r['confidence']} confidence), match={r['match']} -> {r['matched_name']}")
        for x in r["reasons"]:
            print("   -", x)
        if r["related_entities"]:
            print("   similar filers:", "; ".join(r["related_entities"]))
        print("   evidence:", r["evidence"])


if __name__ == "__main__":
    main()
