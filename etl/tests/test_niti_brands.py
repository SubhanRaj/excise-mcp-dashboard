"""sources/niti_brands.py against the real local Postgres via excise_etl.
DATA_PIPELINE.md §Source adapters: a drink type with no seeded `kind` (Wine,
Imported liquor, blank) loads the brand with license_category_id left NULL;
a brand_prices (brand, pack, FY) key with genuinely conflicting price figures
quarantines every row in the group rather than letting the last one win.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import asyncpg
import pytest

from etl.config import settings
from etl.sources.niti_brands import (
    BrandPriceRow,
    BrandRow,
    sync_brand_price_rows,
    sync_brand_rows,
)

TEST_BRAND_PREFIX = "TEST-NITI-BRAND-"


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM brand_prices WHERE brand_id IN "
            "(SELECT id FROM brands WHERE name LIKE $1)",
            f"{TEST_BRAND_PREFIX}%",
        )
        await conn.execute("DELETE FROM brands WHERE name LIKE $1", f"{TEST_BRAND_PREFIX}%")
        await conn.close()


async def _new_run(conn: asyncpg.Connection, source: str = "niti_brands") -> int:
    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref) VALUES ($1, 'test') RETURNING id",
        source,
    )
    assert run_id is not None
    return int(run_id)


async def test_recognized_drink_type_resolves_category(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = BrandRow(
        name=f"{TEST_BRAND_PREFIX}Whisky",
        manufacturer="Test Distillers",
        drink_type_raw="IMFL",
        is_premium=True,
        source_ref="test:001",
    )

    counts = await sync_brand_rows(pg_conn, run_id, [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    stored = await pg_conn.fetchrow(
        "SELECT segment, lc.code FROM brands b "
        "JOIN license_categories lc ON lc.id = b.license_category_id WHERE b.name = $1",
        row.name,
    )
    assert stored is not None
    assert (stored["segment"], stored["code"]) == ("premium", "FL")


async def test_wine_has_no_kind_and_loads_with_null_category(
    pg_conn: asyncpg.Connection,
) -> None:
    run_id = await _new_run(pg_conn)
    row = BrandRow(
        name=f"{TEST_BRAND_PREFIX}Wine",
        manufacturer=None,
        drink_type_raw="Wine",
        is_premium=None,
        source_ref="test:002",
    )

    counts = await sync_brand_rows(pg_conn, run_id, [row])

    assert counts.upserted == 1
    stored = await pg_conn.fetchrow(
        "SELECT license_category_id, segment FROM brands WHERE name = $1", row.name
    )
    assert stored is not None
    assert stored["license_category_id"] is None
    assert stored["segment"] is None


async def test_brand_price_conflict_quarantines_both_rows(pg_conn: asyncpg.Connection) -> None:
    brand_run = await _new_run(pg_conn)
    brand_name = f"{TEST_BRAND_PREFIX}Conflict"
    await sync_brand_rows(
        pg_conn,
        brand_run,
        [
            BrandRow(
                name=brand_name,
                manufacturer=None,
                drink_type_raw="IMFL",
                is_premium=None,
                source_ref="test:003",
            )
        ],
    )

    price_run = await _new_run(pg_conn, source="niti_brand_prices")
    conflicting = [
        BrandPriceRow(
            brand_name=brand_name,
            pack_ml=750,
            financial_year_raw="2024-2025",
            mrp_inr=Decimal("500"),
            ex_distillery_inr=Decimal("400"),
            source_ref="test:price-a",
        ),
        BrandPriceRow(
            brand_name=brand_name,
            pack_ml=750,
            financial_year_raw="2024-2025",
            mrp_inr=Decimal("900"),
            ex_distillery_inr=Decimal("400"),
            source_ref="test:price-b",
        ),
    ]

    counts = await sync_brand_price_rows(pg_conn, price_run, conflicting)

    assert (counts.seen, counts.upserted, counts.quarantined) == (2, 0, 2)
    count = await pg_conn.fetchval(
        "SELECT count(*) FROM brand_prices bp JOIN brands b ON b.id = bp.brand_id "
        "WHERE b.name = $1",
        brand_name,
    )
    assert count == 0


async def test_unknown_brand_is_quarantined(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn, source="niti_brand_prices")
    row = BrandPriceRow(
        brand_name=f"{TEST_BRAND_PREFIX}DoesNotExist",
        pack_ml=750,
        financial_year_raw="2024-2025",
        mrp_inr=Decimal("500"),
        ex_distillery_inr=None,
        source_ref="test:004",
    )

    counts = await sync_brand_price_rows(pg_conn, run_id, [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 0, 1)
