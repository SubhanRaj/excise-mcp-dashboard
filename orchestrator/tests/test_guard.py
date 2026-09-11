"""sql/guard.py — the single-read-only-SELECT parser. ROADMAP.md Milestone 2 tests."""

import pytest

from app.schemas import SqlRejectedError
from app.sql.guard import guard_sql


def test_accepts_plain_select() -> None:
    result = guard_sql("SELECT * FROM analytics.districts", row_limit=100)
    assert "LIMIT 100" in result.sql
    assert result.tables_used == ["districts"]


def test_accepts_with_select() -> None:
    result = guard_sql(
        "WITH d AS (SELECT * FROM analytics.districts) SELECT * FROM d", row_limit=50
    )
    assert "LIMIT 50" in result.sql


def test_preserves_existing_limit() -> None:
    result = guard_sql("SELECT * FROM analytics.districts LIMIT 10", row_limit=5000)
    assert result.sql.count("LIMIT") == 1
    assert "LIMIT 10" in result.sql


def test_rejects_multiple_statements() -> None:
    with pytest.raises(SqlRejectedError, match="exactly one statement"):
        guard_sql("SELECT * FROM analytics.districts; SELECT * FROM analytics.revenues", row_limit=10)


def test_rejects_insert() -> None:
    with pytest.raises(SqlRejectedError):
        guard_sql("INSERT INTO analytics.districts (name) VALUES ('x')", row_limit=10)


def test_rejects_delete() -> None:
    with pytest.raises(SqlRejectedError):
        guard_sql("DELETE FROM analytics.districts", row_limit=10)


def test_rejects_drop() -> None:
    with pytest.raises(SqlRejectedError):
        guard_sql("DROP TABLE analytics.districts", row_limit=10)


def test_rejects_cross_schema_reference() -> None:
    with pytest.raises(SqlRejectedError, match="cross-schema"):
        guard_sql("SELECT * FROM public.districts", row_limit=10)


def test_rejects_etl_schema_reference() -> None:
    with pytest.raises(SqlRejectedError, match="cross-schema"):
        guard_sql("SELECT * FROM etl.ingestion_runs", row_limit=10)


def test_rejects_volatile_function() -> None:
    with pytest.raises(SqlRejectedError, match="forbidden function"):
        guard_sql("SELECT pg_sleep(5)", row_limit=10)


def test_rejects_nextval() -> None:
    with pytest.raises(SqlRejectedError, match="forbidden function"):
        guard_sql("SELECT nextval('some_seq')", row_limit=10)


def test_rejects_unparseable_sql() -> None:
    with pytest.raises(SqlRejectedError):
        guard_sql("not sql at all !!!", row_limit=10)


def test_records_multiple_tables_used() -> None:
    result = guard_sql(
        "SELECT r.* FROM analytics.revenues r JOIN analytics.districts d ON d.id = r.district_id",
        row_limit=10,
    )
    assert set(result.tables_used) == {"revenues", "districts"}
