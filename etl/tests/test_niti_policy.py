"""sources/niti_policy.py against the real local Postgres via excise_etl.
DATA_PIPELINE.md §Source adapters: Policy Rules synthesizes a narrative
summary from a wide row since policy_entries has no per-attribute columns;
every Duty Rates row is quarantined outright (its Rate column is a formula
string, not the plain number duty_rates.rate requires).
"""

from collections.abc import AsyncIterator
from datetime import date

import asyncpg
import pytest

from etl.config import settings
from etl.sources.niti_policy import DutyRateRow, PolicyRow, sync_duty_rate_rows, sync_policy_rows

TEST_SOURCE_REF_PREFIX = "TEST-NITI-POLICY-"


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM policy_entries WHERE source_ref LIKE $1", f"{TEST_SOURCE_REF_PREFIX}%"
        )
        await conn.close()


async def _new_run(conn: asyncpg.Connection, source: str = "niti_policy_rules") -> int:
    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref) VALUES ($1, 'test') RETURNING id",
        source,
    )
    assert run_id is not None
    return int(run_id)


async def test_policy_row_synthesizes_summary_from_wide_columns(
    pg_conn: asyncpg.Connection,
) -> None:
    run_id = await _new_run(pg_conn)
    row = PolicyRow(
        state="Uttar Pradesh",
        financial_year_raw="2014-15",
        fields={
            "Who does the wholesale": "Private wholesaler",
            "Number of distillery licences": 60,
        },
        source_document=None,
        source_ref=f"{TEST_SOURCE_REF_PREFIX}001",
    )

    counts = await sync_policy_rows(pg_conn, run_id, [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    stored = await pg_conn.fetchrow(
        "SELECT title, summary, effective_from, effective_to, category FROM policy_entries "
        "WHERE source_ref = $1",
        f"{TEST_SOURCE_REF_PREFIX}001",
    )
    assert stored is not None
    assert "Uttar Pradesh" in stored["title"]
    assert "Who does the wholesale: Private wholesaler" in stored["summary"]
    assert stored["category"] is None
    assert stored["effective_from"] == date(2014, 4, 1)
    assert stored["effective_to"] == date(2015, 3, 31)


async def test_policy_rerun_upserts_in_place(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = PolicyRow(
        state="Uttar Pradesh",
        financial_year_raw="2015-16",
        fields={"Who does the wholesale": "Private wholesaler"},
        source_document=None,
        source_ref=f"{TEST_SOURCE_REF_PREFIX}002",
    )
    first = await sync_policy_rows(pg_conn, run_id, [row])
    assert first.upserted == 1

    run_id_2 = await _new_run(pg_conn)
    changed = PolicyRow(
        state="Uttar Pradesh",
        financial_year_raw="2015-16",
        fields={"Who does the wholesale": "Government corporation"},
        source_document=None,
        source_ref=f"{TEST_SOURCE_REF_PREFIX}002",
    )
    second = await sync_policy_rows(pg_conn, run_id_2, [changed])
    assert second.upserted == 1

    count = await pg_conn.fetchval(
        "SELECT count(*) FROM policy_entries WHERE source_ref = $1",
        f"{TEST_SOURCE_REF_PREFIX}002",
    )
    assert count == 1
    summary = await pg_conn.fetchval(
        "SELECT summary FROM policy_entries WHERE source_ref = $1",
        f"{TEST_SOURCE_REF_PREFIX}002",
    )
    assert "Government corporation" in summary


async def test_duty_rate_rows_are_all_quarantined(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn, source="niti_duty_rates")
    rows = [
        DutyRateRow(
            state="Uttar Pradesh",
            drink_type="IMFL",
            pack_or_strength="750 ml",
            rate_raw="7.2*EDP",
            unit=None,
            notification="Excise Policy 2014-15",
            source_ref="test:001",
        )
    ]

    counts = await sync_duty_rate_rows(pg_conn, run_id, rows)

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 0, 1)
    quarantined = await pg_conn.fetchval(
        "SELECT reason FROM etl.quarantine WHERE run_id = $1", run_id
    )
    assert "formula" in quarantined
