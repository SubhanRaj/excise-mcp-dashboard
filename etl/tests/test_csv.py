from pathlib import Path

from etl.sources.csv import read_rows


def test_read_rows_yields_one_row_per_data_line(tmp_path: Path) -> None:
    fixture = tmp_path / "sample.csv"
    fixture.write_text("district,metric,value\nLucknow,raids,12\nKanpur,raids,8\n")

    rows = list(read_rows(str(fixture), "operations"))

    assert len(rows) == 2
    assert rows[0].fields == {"district": "Lucknow", "metric": "raids", "value": "12"}
    assert rows[0].source_ref == f"csv:{fixture}:1"
    assert rows[0].target_table == "operations"


def test_read_rows_is_idempotent_on_repeat_read(tmp_path: Path) -> None:
    fixture = tmp_path / "sample.csv"
    fixture.write_text("district,metric,value\nLucknow,raids,12\n")

    first = [r.fields for r in read_rows(str(fixture), "operations")]
    second = [r.fields for r in read_rows(str(fixture), "operations")]

    assert first == second
