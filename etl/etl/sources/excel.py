"""NITI submission workbooks. DATA_PIPELINE.md §Source adapters:
- a row is data if its natural-key columns are all present and numeric-or-text
  as declared, not the sibling's old heuristic on column A's length
- one workbook can feed several sheets -> several target tables; the column
  map (name in the sheet -> normalized field) is per sheet

The per-sheet column map for the real NITI workbooks isn't written yet — the
source files are still being finalized (ROADMAP.md Milestone 1). This reader
is complete and tested against a synthetic fixture (tests/test_excel.py); a
`SHEET_MAPS` entry gets added here per sheet once the final layout is in hand.
"""

from collections.abc import Iterator

import openpyxl

from etl.sources.base import RawRow

# sheet name -> (target_table, natural-key column names as they appear in the
# sheet's header row). Empty until the real workbook layout is confirmed.
SHEET_MAPS: dict[str, tuple[str, tuple[str, ...]]] = {}


def read_rows(source_ref: str, sheet_name: str, target_table: str) -> Iterator[RawRow]:
    key_columns = SHEET_MAPS.get(sheet_name, (target_table, ()))[1]
    workbook = openpyxl.load_workbook(source_ref, read_only=True, data_only=True)
    sheet = workbook[sheet_name]
    rows = sheet.iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]

    for i, values in enumerate(rows, start=2):  # header is row 1
        fields = {header[j]: ("" if v is None else str(v)) for j, v in enumerate(values)}
        if key_columns and not _has_key_data(fields, key_columns):
            continue  # not a data row (blank / note / subtotal line)
        yield RawRow(
            target_table=target_table,
            fields=fields,
            source_ref=f"excel:{source_ref}:{sheet_name}:{i}",
        )
    workbook.close()


def _has_key_data(fields: dict[str, str], key_columns: tuple[str, ...]) -> bool:
    return all(fields.get(col, "").strip() for col in key_columns)
