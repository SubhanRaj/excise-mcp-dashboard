"""Excel reader against a synthetic fixture — not the real NITI workbook layout
(that column map is added to etl/sources/excel.py's SHEET_MAPS once the source
files are finalized), just proof the reader parses a sheet into RawRow and
skips a non-data row.
"""

from pathlib import Path

import openpyxl

from etl.sources.excel import read_rows


def _write_fixture(path: Path) -> None:
    wb = openpyxl.Workbook()
    assert wb.active is not None
    sheet = wb.active
    sheet.title = "Operations"
    sheet.append(["district", "financial_year", "metric", "value"])
    sheet.append(["Lucknow", "2014-15", "raids", "12"])
    sheet.append(["Note: figures provisional", None, None, None])  # not a data row
    sheet.append(["Kanpur", "2014-15", "raids", "8"])
    wb.save(path)


def test_read_rows_skips_rows_missing_key_columns(tmp_path: Path) -> None:
    from etl.sources import excel

    fixture = tmp_path / "sample.xlsx"
    _write_fixture(fixture)
    excel.SHEET_MAPS["Operations"] = ("operations", ("district", "metric"))

    try:
        rows = list(read_rows(str(fixture), "Operations", "operations"))
    finally:
        del excel.SHEET_MAPS["Operations"]

    assert [r.fields["district"] for r in rows] == ["Lucknow", "Kanpur"]
    assert rows[0].source_ref == f"excel:{fixture}:Operations:2"
