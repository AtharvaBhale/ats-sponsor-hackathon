import csv
import sqlite3

import pytest
from openpyxl import Workbook

from src.app import sponsor_data, tabular

USCIS_HDR = ["Fiscal Year", "Employer", "Initial Approval", "Initial Denial",
             "Continuing Approval", "Continuing Denial", "NAICS", "Tax ID", "State", "City", "ZIP"]


def write_csv(path, header, rows, delim=",", encoding="utf-8"):
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f, delimiter=delim)
        w.writerow(header)
        w.writerows(rows)


def test_reads_utf16_tab_and_utf8_comma(tmp_path):
    rows = [[2024, "NORTHWIND ANALYTICS, INC.", "1,234", 1, 5, 0, "54", "1234", "WA", "X", "98"]]
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_csv(a, USCIS_HDR, rows, "\t", "utf-16")
    write_csv(b, USCIS_HDR, rows, ",", "utf-8-sig")
    for p in (a, b):
        assert tabular.headers(p)[:2] == ["Fiscal Year", "Employer"]
        assert next(tabular.iter_rows(p))["Initial Approval"] == "1,234"


def test_reads_xlsx_and_filters_columns(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["EMPLOYER_NAME", "EXTRA", "CASE_STATUS"])
    ws.append(["Acme", "junk", "Certified"])
    ws.append([None, None, None])
    p = tmp_path / "x.xlsx"
    wb.save(p)
    rows = list(tabular.iter_rows(p, {"employername", "casestatus"}))
    assert rows == [{"EMPLOYER_NAME": "Acme", "CASE_STATUS": "Certified"}]


def test_build_uscis_aggregates_name_variants_and_years(tmp_path):
    p = tmp_path / "u.csv"
    write_csv(p, USCIS_HDR, [
        [2024, "NORTHWIND ANALYTICS INC", 3, 0, 2, 0, "54", "1", "WA", "A", "1"],
        [2024, "Northwind Analytics, LLC", "2", 1, 0, 0, "54", "2", "WA", "B", "2"],
        [2023, "Northwind Analytics Inc.", 4, 0, 1, 0, "54", "1", "WA", "A", "1"],
    ])
    out = tmp_path / "s.db"
    s = sponsor_data.build(out, [(None, p)])
    db = sqlite3.connect(out)
    assert db.execute("SELECT ia,id,ca,cd FROM uscis WHERE norm='northwind analytics' AND fy=2024"
                      ).fetchone() == (5, 1, 2, 0)
    assert db.execute("SELECT COUNT(*) FROM uscis").fetchone()[0] == 2
    assert s["uscis_fys"] == "2023,2024"


def test_build_lca_filters_dedupes_and_counts(tmp_path):
    hdr = ["CASE_NUMBER", "CASE_STATUS", "VISA_CLASS", "EMPLOYER_NAME", "EMPLOYER_STATE",
           "WORKSITE_STATE", "SECONDARY_ENTITY", "H-1B_DEPENDENT", "NAICS_CODE"]
    rows = [
        ["C1", "Certified", "H-1B", "Globex Talent LLC", "NJ", "TX", "Y", "Y", "541511"],
        ["C1", "Certified", "H-1B", "Globex Talent LLC", "NJ", "TX", "Y", "Y", "541511"],  # dup
        ["C2", "Denied", "H-1B", "Globex Talent LLC", "NJ", "NJ", "N", "Y", "541511"],
        ["C3", "Certified", "H-1B1 Chile", "Globex Talent LLC", "NJ", "NJ", "N", "N", "541511"],
        ["C4", "Certified", "E-3 Australian", "Globex Talent LLC", "NJ", "NJ", "N", "N", "541511"],
    ]
    p = tmp_path / "l.csv"
    write_csv(p, hdr, rows)
    out = tmp_path / "s.db"
    s = sponsor_data.build(out, [], [(2026, p)])
    row = sqlite3.connect(out).execute(
        "SELECT certified,total,sec_known,sec_yes,mm_known,mm_yes,dependent FROM lca").fetchone()
    assert row == (1, 2, 2, 1, 2, 1, 2)
    assert s["lca_duplicates"] == 1 and s["lca_kept"] == 2
    assert sqlite3.connect(out).execute("SELECT naics FROM employer").fetchone()[0] == "541511"


def test_missing_columns_error_lists_headers(tmp_path):
    p = tmp_path / "bad.csv"
    write_csv(p, ["Foo", "Bar"], [[1, 2]])
    with pytest.raises(sponsor_data.DataError) as e:
        sponsor_data.build(tmp_path / "s.db", [(2024, p)])
    assert "Foo" in str(e.value) and "Bar" in str(e.value)


def test_lca_without_status_warns(tmp_path):
    p = tmp_path / "l.csv"
    write_csv(p, ["EMPLOYER_NAME"], [["Acme Inc"]])
    s = sponsor_data.build(tmp_path / "s.db", [], [(2026, p)])
    assert any("CASE_STATUS" in w for w in s["warnings"])
