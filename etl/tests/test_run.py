"""run.py's --period gate against the real local Postgres via excise_etl.
DATA_PIPELINE.md §Periodic sources without a per-row date: a source_registry
row marked requires_period refuses to run without --period, and records the
declared period on its etl.ingestion_runs row when one is given.
"""

from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import asyncpg
import pytest

from etl.config import settings
from etl.run import _parse_period, _run_source

TEST_SOURCE_PREFIX = "TEST-RUN-"


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        # source_registry.last_run_id references ingestion_runs, so it goes first.
        await conn.execute(
            "DELETE FROM etl.source_registry WHERE name LIKE $1", f"{TEST_SOURCE_PREFIX}%"
        )
        await conn.execute(
            "DELETE FROM etl.ingestion_runs WHERE source_ref LIKE $1", f"{TEST_SOURCE_PREFIX}%"
        )
        await conn.close()


async def _registry_row(
    conn: asyncpg.Connection, *, name: str, source_ref: str, requires_period: bool
) -> asyncpg.Record:
    registry_id = await conn.fetchval(
        "INSERT INTO etl.source_registry (name, source, source_ref, target_table, schedule, "
        "requires_period) VALUES ($1, 'csv', $2, 'operations', '@monthly', $3) RETURNING id",
        name,
        source_ref,
        requires_period,
    )
    row = await conn.fetchrow("SELECT * FROM etl.source_registry WHERE id = $1", registry_id)
    assert row is not None
    return row


def test_parse_period_resolves_to_the_first_of_the_month() -> None:
    assert _parse_period("2026-08") == date(2026, 8, 1)
    assert _parse_period(None) is None


async def test_a_source_requiring_a_period_fails_without_one(pg_conn: asyncpg.Connection) -> None:
    registry_row = await _registry_row(
        pg_conn,
        name=f"{TEST_SOURCE_PREFIX}no-period",
        source_ref=f"{TEST_SOURCE_PREFIX}no-period",
        requires_period=True,
    )

    await _run_source(pg_conn, registry_row, None)

    run = await pg_conn.fetchrow(
        "SELECT status, report_period, error FROM etl.ingestion_runs WHERE source_ref = $1",
        registry_row["source_ref"],
    )
    assert run is not None
    assert run["status"] == "failed"
    assert run["report_period"] is None
    assert "--period" in run["error"]


async def test_a_source_requiring_a_period_records_it_when_given(
    pg_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    fixture = tmp_path / "sample.csv"
    fixture.write_text("district,metric,value\nLucknow,raids,12\n")
    registry_row = await _registry_row(
        pg_conn,
        name=f"{TEST_SOURCE_PREFIX}with-period",
        source_ref=str(fixture),
        requires_period=True,
    )

    await _run_source(pg_conn, registry_row, date(2026, 8, 1))

    run = await pg_conn.fetchrow(
        "SELECT report_period FROM etl.ingestion_runs WHERE source_ref = $1",
        registry_row["source_ref"],
    )
    assert run is not None
    assert run["report_period"] == date(2026, 8, 1)


async def test_a_source_not_requiring_a_period_runs_regardless(
    pg_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    fixture = tmp_path / "sample.csv"
    fixture.write_text("district,metric,value\nLucknow,raids,12\n")
    registry_row = await _registry_row(
        pg_conn,
        name=f"{TEST_SOURCE_PREFIX}no-flag",
        source_ref=str(fixture),
        requires_period=False,
    )

    await _run_source(pg_conn, registry_row, None)

    run = await pg_conn.fetchrow(
        "SELECT status, report_period FROM etl.ingestion_runs WHERE source_ref = $1",
        registry_row["source_ref"],
    )
    assert run is not None
    assert run["status"] != "failed"
    assert run["report_period"] is None
