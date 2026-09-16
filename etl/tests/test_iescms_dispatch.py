"""sources/iescms_dispatch.py — _financial_year_start() (pure) and sync_rows()
against the real local Postgres via excise_etl. DATA_PIPELINE.md §Dispatches:
a shop upserts on (district_id, shop_number, seq); a dispatch upserts on
indent_number; a country-liquor row's per-strength lines land in
dispatch_strength_lines; an unknown license category is quarantined, not
guessed at.
"""

from collections.abc import AsyncIterator
from datetime import datetime

import asyncpg
import pytest

from etl.config import settings
from etl.sources.iescms_dispatch import DispatchRow, StrengthLine, _financial_year_start, sync_rows

TEST_INDENT_PREFIX = "TEST-IESCMS-"


def _row(indent_suffix: str, **overrides: object) -> DispatchRow:
    base = dict(
        district_name="Lucknow",
        wholesale_license_type="FL2",
        wholesale_license_number="LIC/WHOLESALE/TEST",
        wholesale_entity_name="Test Wholesaler",
        retail_shop_ref="9999901",
        retail_entity_name="Test Retail Shop",
        retail_license_type="FL",  # a pre-existing broad code, no seed_reference.sql dependency
        circle_sector="Sector - 1",
        indent_number=f"{TEST_INDENT_PREFIX}{indent_suffix}",
        indent_received_at=datetime(2026, 8, 1),
        indent_accepted_at=datetime(2026, 8, 1),
        transport_pass_issued_at=datetime(2026, 8, 2),
        tp_reference_no="TP-TEST-0001",
        dispatched_bulk_litres=100.0,
        duty_fee_inr=5000.0,
        source_ref="test",
    )
    base.update(overrides)
    return DispatchRow(**base)  # type: ignore[arg-type]


def test_financial_year_start_before_april_belongs_to_the_prior_fy() -> None:
    assert _financial_year_start(datetime(2026, 8, 1)) == 2026
    assert _financial_year_start(datetime(2026, 1, 15)) == 2025
    assert _financial_year_start(datetime(2026, 4, 1)) == 2026


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM dispatches WHERE indent_number LIKE $1", f"{TEST_INDENT_PREFIX}%"
        )
        await conn.execute(
            "DELETE FROM shops WHERE shop_number IN ('9999901', '9999902')",
        )
        await conn.close()


async def _new_run(conn: asyncpg.Connection) -> int:
    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref) "
        "VALUES ('iescms_dispatch', 'test') RETURNING id"
    )
    assert run_id is not None
    return int(run_id)


async def test_sync_creates_shop_and_dispatch(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)

    counts = await sync_rows(pg_conn, run_id, [_row("001")])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    shop = await pg_conn.fetchrow("SELECT display_name FROM shops WHERE shop_number = '9999901'")
    assert shop is not None
    assert shop["display_name"] == "Test Retail Shop"
    dispatch = await pg_conn.fetchrow(
        "SELECT dispatched_bulk_litres, duty_fee_inr FROM dispatches WHERE indent_number = $1",
        f"{TEST_INDENT_PREFIX}001",
    )
    assert dispatch is not None
    assert float(dispatch["dispatched_bulk_litres"]) == 100.0


async def test_rerun_upserts_nothing_new(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    first = await sync_rows(pg_conn, run_id, [_row("002")])
    assert first.upserted == 1

    run_id_2 = await _new_run(pg_conn)
    second = await sync_rows(pg_conn, run_id_2, [_row("002")])
    assert second.upserted == 1  # re-run still "upserts" (ON CONFLICT DO UPDATE), but one row total

    count = await pg_conn.fetchval(
        "SELECT count(*) FROM dispatches WHERE indent_number = $1", f"{TEST_INDENT_PREFIX}002"
    )
    assert count == 1


async def test_country_liquor_strength_lines_are_stored(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _row(
        "003",
        wholesale_license_type="CL2",
        retail_license_type="CL",
        retail_shop_ref="9999902",
        strength_lines=(
            StrengthLine(
                strength_label="25% V/V",
                requested_cases=10.0,
                requested_bulk_litres=90.0,
                dispatched_cases=10.0,
                dispatched_bulk_litres=90.0,
            ),
        ),
    )

    counts = await sync_rows(pg_conn, run_id, [row])

    assert counts.upserted == 1
    line = await pg_conn.fetchrow(
        "SELECT sl.dispatched_bulk_litres FROM dispatch_strength_lines sl "
        "JOIN dispatches d ON d.id = sl.dispatch_id WHERE d.indent_number = $1",
        f"{TEST_INDENT_PREFIX}003",
    )
    assert line is not None
    assert float(line["dispatched_bulk_litres"]) == 90.0


async def test_unknown_license_category_is_quarantined(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _row("004", retail_license_type="NOT-A-REAL-CODE")

    counts = await sync_rows(pg_conn, run_id, [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 0, 1)
