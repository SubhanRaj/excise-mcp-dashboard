"""sources/niti_shops.py against the real local Postgres via excise_etl.
DATA_PIPELINE.md §Shops: a category with a seeded code resolves
license_category_id; one without (Other/Retail/Bar/Wholesale Beer & Wine)
loads the shop anyway with license_category_id left NULL. A flagged
district's rows load unpublished. A Lucknow shop_number that collides with an
existing IESCMS-origin row is quarantined, not merged or duplicated.
"""

from collections.abc import AsyncIterator

import asyncpg
import pytest

from etl.config import settings
from etl.sources.niti_shops import ShopRow, sync_rows

TEST_SHOP_PREFIX = "TEST-NITI-SHOP-"


def _row(shop_number: str, district_sheet: str = "AGRA", **overrides: object) -> ShopRow:
    base = dict(
        district_sheet=district_sheet,
        shop_number=shop_number,
        seq=1,
        financial_year_raw="2014-2015",
        shop_type_raw="Country Liquor",
        allotment_method="auction",
        license_fee=None,
        min_imfl=None,
        min_country_liquor=None,
        min_beer=None,
        unit=None,
        gave_up_shop=None,
        source_ref=f"test:{shop_number}",
    )
    base.update(overrides)
    return ShopRow(**base)  # type: ignore[arg-type]


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM shop_years WHERE shop_id IN "
            "(SELECT id FROM shops WHERE shop_number LIKE $1)",
            f"{TEST_SHOP_PREFIX}%",
        )
        await conn.execute("DELETE FROM shops WHERE shop_number LIKE $1", f"{TEST_SHOP_PREFIX}%")
        await conn.close()


async def _new_run(conn: asyncpg.Connection) -> int:
    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref) VALUES ('niti_shops', 'test') "
        "RETURNING id"
    )
    assert run_id is not None
    return int(run_id)


async def test_mapped_category_resolves_license_category_id(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _row(f"{TEST_SHOP_PREFIX}001", shop_type_raw="Beer")

    counts = await sync_rows(pg_conn, run_id, [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    stored = await pg_conn.fetchrow(
        "SELECT lc.code FROM shops s JOIN license_categories lc ON lc.id = s.license_category_id "
        "WHERE s.shop_number = $1",
        f"{TEST_SHOP_PREFIX}001",
    )
    assert stored is not None
    assert stored["code"] == "BEER"


async def test_unmapped_category_loads_shop_with_null_category(
    pg_conn: asyncpg.Connection,
) -> None:
    run_id = await _new_run(pg_conn)
    row = _row(f"{TEST_SHOP_PREFIX}002", shop_type_raw="Other")

    counts = await sync_rows(pg_conn, run_id, [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    stored = await pg_conn.fetchrow(
        "SELECT license_category_id FROM shops WHERE shop_number = $1",
        f"{TEST_SHOP_PREFIX}002",
    )
    assert stored is not None
    assert stored["license_category_id"] is None


async def test_flagged_district_loads_unpublished(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _row(f"{TEST_SHOP_PREFIX}003", district_sheet="AZAMGARH")

    counts = await sync_rows(pg_conn, run_id, [row])

    assert counts.upserted == 1
    stored = await pg_conn.fetchrow(
        "SELECT published_at FROM shops WHERE shop_number = $1", f"{TEST_SHOP_PREFIX}003"
    )
    assert stored is not None
    assert stored["published_at"] is None


async def test_non_flagged_district_loads_published(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _row(f"{TEST_SHOP_PREFIX}004", district_sheet="AGRA")

    await sync_rows(pg_conn, run_id, [row])

    stored = await pg_conn.fetchrow(
        "SELECT published_at FROM shops WHERE shop_number = $1", f"{TEST_SHOP_PREFIX}004"
    )
    assert stored is not None
    assert stored["published_at"] is not None


async def test_blank_shop_type_is_quarantined(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _row(f"{TEST_SHOP_PREFIX}005", shop_type_raw=None)

    counts = await sync_rows(pg_conn, run_id, [row])

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 0, 1)


async def test_lucknow_collision_with_existing_shop_is_quarantined(
    pg_conn: asyncpg.Connection,
) -> None:
    lucknow_id = await pg_conn.fetchval("SELECT id FROM districts WHERE name = 'Lucknow'")
    existing_number = f"{TEST_SHOP_PREFIX}COLLIDE"
    await pg_conn.execute(
        "INSERT INTO shops (district_id, shop_number, seq, display_name, published_at) "
        "VALUES ($1, $2, 1, 'existing IESCMS shop', now())",
        lucknow_id,
        existing_number,
    )
    try:
        run_id = await _new_run(pg_conn)
        row = _row(existing_number, district_sheet="LUCKNOW")

        counts = await sync_rows(pg_conn, run_id, [row])

        assert (counts.seen, counts.upserted, counts.quarantined) == (1, 0, 1)
    finally:
        await pg_conn.execute("DELETE FROM shops WHERE shop_number = $1", existing_number)


async def test_lucknow_rerun_of_own_prior_rows_is_not_a_collision(
    pg_conn: asyncpg.Connection,
) -> None:
    """Regression test: a shop this same niti_shops source already inserted on an
    earlier run must not be flagged as colliding with itself on the next run -
    only a shop with no niti_shops-origin shop_years row (genuine IESCMS-only
    data) counts as a real collision.
    """
    own_number = f"{TEST_SHOP_PREFIX}OWNRUN"
    row = _row(own_number, district_sheet="LUCKNOW")

    first_run = await _new_run(pg_conn)
    first = await sync_rows(pg_conn, first_run, [row])
    assert (first.upserted, first.quarantined) == (1, 0)

    second_run = await _new_run(pg_conn)
    second = await sync_rows(pg_conn, second_run, [row])
    assert (second.upserted, second.quarantined) == (1, 0)

    count = await pg_conn.fetchval("SELECT count(*) FROM shops WHERE shop_number = $1", own_number)
    assert count == 1


async def test_duplicate_seq_in_same_year_upserts_as_two_shops(pg_conn: asyncpg.Connection) -> None:
    """A generic shop name repeating within one district+FY (CLAUDE.md's
    per-district-merge notes) must not collapse two real licence records into
    one - read_shop_rows assigns each occurrence its own seq; sync_rows must
    keep them as two distinct `shops` rows.
    """
    run_id = await _new_run(pg_conn)
    shared_name = f"{TEST_SHOP_PREFIX}SHARED"
    rows = [_row(shared_name, seq=1), _row(shared_name, seq=2, shop_type_raw="Beer")]

    counts = await sync_rows(pg_conn, run_id, rows)

    assert counts.upserted == 2
    count = await pg_conn.fetchval("SELECT count(*) FROM shops WHERE shop_number = $1", shared_name)
    assert count == 2
