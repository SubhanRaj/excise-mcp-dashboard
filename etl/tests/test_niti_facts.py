"""sources/niti_facts.py against the real local Postgres via excise_etl.
DATA_PIPELINE.md §Source adapters: a blank cell is skipped, not inserted as
zero; a re-run upserts in place even though license_category_id is always
NULL for this source (the NULL-never-conflicts gap `_upsert_revenue_or_sales`
works around, see its own comment).
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import asyncpg
import pytest

from etl.config import settings
from etl.sources.niti_facts import (
    FactRow,
    sync_operations_rows,
    sync_revenue_or_sales_rows,
)

TEST_SOURCE_REF_PREFIX = "TEST-NITI-FACTS-"


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM revenues WHERE source_ref LIKE $1", f"{TEST_SOURCE_REF_PREFIX}%"
        )
        await conn.execute(
            "DELETE FROM sales_volumes WHERE source_ref LIKE $1", f"{TEST_SOURCE_REF_PREFIX}%"
        )
        await conn.execute(
            "DELETE FROM operations WHERE source_ref LIKE $1", f"{TEST_SOURCE_REF_PREFIX}%"
        )
        await conn.close()


async def _new_run(conn: asyncpg.Connection) -> int:
    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref) VALUES ('niti_facts', 'test') "
        "RETURNING id"
    )
    assert run_id is not None
    return int(run_id)


def _revenue_row(suffix: str, **overrides: object) -> FactRow:
    # `metric` defaults to a value no real metric slug will ever be (never
    # "excise_duty"/"imfl"/etc): revenues/sales_volumes/operations upsert on
    # (district_id, financial_year_id, metric[, license_category_id]), which
    # does NOT include source_ref - a real district + a real-looking FY here
    # with a REAL metric name would hit the exact natural key of a genuine
    # production row, silently overwrite its value, and then delete it on
    # teardown (this happened once already: Agra FY2014-15's real excise_duty
    # and imfl rows were wiped this way before this comment existed).
    base = dict(
        district_name="Agra",
        financial_year_raw="2014-15",
        metric=f"__test_metric_{suffix}__",
        value=Decimal("1000.00"),
        unit=None,
        source_ref=f"{TEST_SOURCE_REF_PREFIX}{suffix}",
    )
    base.update(overrides)
    return FactRow(**base)  # type: ignore[arg-type]


async def test_revenue_row_inserts_with_null_category(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)

    counts = await sync_revenue_or_sales_rows(
        pg_conn, run_id, "revenues", "amount_inr", [_revenue_row("001")]
    )

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    row = await pg_conn.fetchrow(
        "SELECT amount_inr, license_category_id FROM revenues WHERE source_ref = $1",
        f"{TEST_SOURCE_REF_PREFIX}001",
    )
    assert row is not None
    assert row["license_category_id"] is None
    assert Decimal(row["amount_inr"]) == Decimal("1000.00")


async def test_revenue_rerun_updates_in_place_not_duplicates(pg_conn: asyncpg.Connection) -> None:
    """The regression test for the bug this module's manual upsert fixes: a
    plain ON CONFLICT on a key with a NULL column never fires, so a naive
    upsert would insert a fresh duplicate row on every re-run.
    """
    run_id = await _new_run(pg_conn)
    first = await sync_revenue_or_sales_rows(
        pg_conn, run_id, "revenues", "amount_inr", [_revenue_row("002")]
    )
    assert first.upserted == 1

    run_id_2 = await _new_run(pg_conn)
    changed = _revenue_row("002", value=Decimal("2500.00"))
    second = await sync_revenue_or_sales_rows(
        pg_conn, run_id_2, "revenues", "amount_inr", [changed]
    )
    assert second.upserted == 1

    count = await pg_conn.fetchval(
        "SELECT count(*) FROM revenues WHERE source_ref = $1", f"{TEST_SOURCE_REF_PREFIX}002"
    )
    assert count == 1
    amount = await pg_conn.fetchval(
        "SELECT amount_inr FROM revenues WHERE source_ref = $1", f"{TEST_SOURCE_REF_PREFIX}002"
    )
    assert Decimal(amount) == Decimal("2500.00")


async def test_sales_volume_requires_a_unit(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _revenue_row("003", unit=None)

    counts = await sync_revenue_or_sales_rows(pg_conn, run_id, "sales_volumes", "quantity", [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 0, 1)


async def test_sales_volume_row_inserts_with_unit(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _revenue_row("004", value=Decimal("500.5"), unit="Bulk litres")

    counts = await sync_revenue_or_sales_rows(pg_conn, run_id, "sales_volumes", "quantity", [row])

    assert counts.upserted == 1
    stored = await pg_conn.fetchrow(
        "SELECT quantity, unit FROM sales_volumes WHERE source_ref = $1",
        f"{TEST_SOURCE_REF_PREFIX}004",
    )
    assert stored is not None
    assert stored["unit"] == "Bulk litres"


async def test_operations_row_upserts_on_natural_key(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _revenue_row("005", value=Decimal("42"))

    first = await sync_operations_rows(pg_conn, run_id, [row])
    assert first.upserted == 1

    run_id_2 = await _new_run(pg_conn)
    changed = _revenue_row("005", value=Decimal("50"))
    second = await sync_operations_rows(pg_conn, run_id_2, [changed])
    assert second.upserted == 1

    count = await pg_conn.fetchval(
        "SELECT count(*) FROM operations WHERE source_ref = $1", f"{TEST_SOURCE_REF_PREFIX}005"
    )
    assert count == 1


async def test_unknown_district_is_quarantined(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _revenue_row("006", district_name="Not A Real District")

    counts = await sync_revenue_or_sales_rows(pg_conn, run_id, "revenues", "amount_inr", [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 0, 1)
