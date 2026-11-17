"""Company-name normalisation. Reused by staffing detection and sponsorship matching."""
import re

_SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "lp", "llp",
             "pllc", "plc", "limited", "incorporated", "pc", "gmbh"}


def normalize_company(name: str) -> str:
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = s.split()
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)
