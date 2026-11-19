"""Streaming readers for CSV/TSV/XLSX files with unknown encoding, delimiter and headers."""
import csv
import re
from pathlib import Path


def norm_header(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h or "").lower())


def _encoding(path) -> str:
    with open(path, "rb") as f:
        chunk = f.read(65536)
    if chunk[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    if chunk[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start < len(chunk) - 4:  # real error, not a split multibyte char at the cut
            return "latin-1"
    return "utf-8"


def _open_csv(path):
    f = open(path, encoding=_encoding(path), errors="replace", newline="")
    first = f.readline()
    f.seek(0)
    delim = max([",", "\t", ";", "|"], key=first.count)
    return f, delim


def headers(path) -> list:
    path = str(path)
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            first = next(wb.worksheets[0].iter_rows(values_only=True), ())
            return [str(h).strip() for h in first if h is not None and str(h).strip()]
        finally:
            wb.close()
    f, delim = _open_csv(path)
    with f:
        row = next(csv.reader(f, delimiter=delim), [])
    return [h.strip().lstrip("\ufeff") for h in row if h.strip()]


def iter_rows(path, keep_norm: set | None = None):
    """Yield {original_header: value}. keep_norm limits columns (by norm_header) for speed."""
    path = str(path)
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            rows = wb.worksheets[0].iter_rows(values_only=True)
            hdr = [str(h).strip() if h is not None else "" for h in next(rows, ())]
            idx = [(i, h) for i, h in enumerate(hdr)
                   if h and (keep_norm is None or norm_header(h) in keep_norm)]
            for r in rows:
                if r is None or all(v in (None, "") for v in r):
                    continue
                yield {h: ("" if i >= len(r) or r[i] is None else str(r[i]).strip())
                       for i, h in idx}
        finally:
            wb.close()
        return
    f, delim = _open_csv(path)
    with f:
        reader = csv.DictReader(f, delimiter=delim)
        for row in reader:
            row = {(k or "").strip().lstrip("\ufeff"): (v or "").strip() for k, v in row.items()}
            if not any(row.values()):
                continue
            if keep_norm is not None:
                row = {k: v for k, v in row.items() if norm_header(k) in keep_norm}
            yield row
