"""sources/sro_shops.py — read_rows() against a small fixture dump (pure, no
DB) and sync_rows() against the real local Postgres via excise_etl.
DATA_PIPELINE.md §SRO shop revenue snapshot: a shop upserts on (district_id,
source_shop_id, financial_year_id); an unknown district is quarantined, not
guessed at; a re-run of the same snapshot changes no row count.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

from etl.config import settings
from etl.sources.sro_shops import SroShopRow, read_rows, sync_rows

TEST_SHOP_ID_PREFIX = "TEST-SRO-"

_FIXTURE_DUMP = """
CREATE TABLE phase1_raw_collection (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  district_name TEXT NOT NULL,
  circle_sector_name TEXT NOT NULL,
  thana_name TEXT NOT NULL,
  shop_id TEXT NOT NULL,
  shop_name TEXT NOT NULL,
  shop_type TEXT NOT NULL,
  has_cl5cc INTEGER NOT NULL DEFAULT 0,
  latitude_decimal REAL,
  longitude_decimal REAL,
  license_fee_lf INTEGER DEFAULT 0,
  basic_license_fee_blf INTEGER DEFAULT 0,
  mgr_amount INTEGER DEFAULT 0,
  composite_lf_fl INTEGER DEFAULT 0,
  composite_lf_beer INTEGER DEFAULT 0,
  composite_mgr_fl INTEGER DEFAULT 0,
  composite_mgr_beer INTEGER DEFAULT 0,
  mgq_quantity INTEGER DEFAULT 0,
  consideration_fee INTEGER DEFAULT 0,
  special_beer_lf INTEGER DEFAULT 0,
  special_beer_mgr INTEGER DEFAULT 0,
  total_revenue INTEGER NOT NULL DEFAULT 0,
  uploaded_by_deo TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
INSERT INTO phase1_raw_collection VALUES
  (501,'Lucknow','Circle 1 - Sadar','Hazratganj','TEST-SRO-001','Test Shop One',
   'COMPOSITE_SHOP',0,26.85,80.94,100000,0,900000,50000,20000,600000,300000,0,0,0,0,
   1050000,'DEO-TEST',1700000000);
INSERT INTO phase1_raw_collection VALUES
  (502,'Lucknow','Circle 1 - Sadar','Hazratganj','TEST-SRO-002','Test Shop Two',
   'COMPOSITE_SHOP',0,26.854419,80915631.0,100000,0,900000,50000,20000,600000,300000,0,0,0,0,
   1050000,'DEO-TEST',1700000000);
"""


def _write_fixture(tmp_path: Path) -> str:
    dump_path = tmp_path / "fixture-backup.sql"
    dump_path.write_text(_FIXTURE_DUMP)
    return str(dump_path)


def test_read_rows_parses_the_dump(tmp_path: Path) -> None:
    rows = read_rows(_write_fixture(tmp_path))

    assert len(rows) == 2
    row = rows[0]
    assert row.district_name == "Lucknow"
    assert row.source_shop_id == "TEST-SRO-001"
    assert row.total_revenue == 1050000
    assert row.has_cl5cc is False
    assert row.latitude == 26.85


def test_read_rows_drops_an_out_of_range_coordinate(tmp_path: Path) -> None:
    # Confirmed live: SRO's own dump has 5 rows (of 28,405) with a decimal point
    # dropped during data entry, e.g. longitude 80915631.0 instead of 80.915631 —
    # the shop's own revenue figures are still good, only the bad coordinate drops.
    rows = read_rows(_write_fixture(tmp_path))

    bad_row = next(r for r in rows if r.source_shop_id == "TEST-SRO-002")
    assert bad_row.latitude == 26.854419
    assert bad_row.longitude is None
    assert bad_row.total_revenue == 1050000


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM sro_shops WHERE source_shop_id LIKE $1", f"{TEST_SHOP_ID_PREFIX}%"
        )
        await conn.close()


async def _new_run(conn: asyncpg.Connection) -> int:
    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref) VALUES ('sro_shops', 'test') "
        "RETURNING id"
    )
    assert run_id is not None
    return int(run_id)


def _row(shop_suffix: str, **overrides: object) -> SroShopRow:
    base = dict(
        district_name="Lucknow",
        circle_sector_name="Circle 1 - Sadar",
        thana_name="Hazratganj",
        source_shop_id=f"{TEST_SHOP_ID_PREFIX}{shop_suffix}",
        shop_name="Test Shop",
        shop_type="COMPOSITE_SHOP",
        has_cl5cc=False,
        latitude=26.85,
        longitude=80.94,
        license_fee_lf=100000.0,
        basic_license_fee_blf=0.0,
        mgr_amount=900000.0,
        composite_lf_fl=50000.0,
        composite_lf_beer=20000.0,
        composite_mgr_fl=600000.0,
        composite_mgr_beer=300000.0,
        mgq_quantity=0.0,
        consideration_fee=0.0,
        special_beer_lf=0.0,
        special_beer_mgr=0.0,
        total_revenue=1050000.0,
        uploaded_by_deo="DEO-TEST",
        source_ref="test",
    )
    base.update(overrides)
    return SroShopRow(**base)  # type: ignore[arg-type]


async def test_sync_creates_shop(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)

    counts = await sync_rows(pg_conn, run_id, [_row("001")], "FY2025-26")

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    shop = await pg_conn.fetchrow(
        "SELECT shop_name, total_revenue, thana_name FROM sro_shops WHERE source_shop_id = $1",
        f"{TEST_SHOP_ID_PREFIX}001",
    )
    assert shop is not None
    assert shop["shop_name"] == "Test Shop"
    assert float(shop["total_revenue"]) == 1050000.0
    assert shop["thana_name"] == "Hazratganj"


async def test_rerun_upserts_nothing_new(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    first = await sync_rows(pg_conn, run_id, [_row("002")], "FY2025-26")
    assert first.upserted == 1

    run_id_2 = await _new_run(pg_conn)
    second = await sync_rows(pg_conn, run_id_2, [_row("002", total_revenue=2000000.0)], "FY2025-26")
    assert second.upserted == 1  # ON CONFLICT DO UPDATE — one row, updated in place

    rows = await pg_conn.fetch(
        "SELECT total_revenue FROM sro_shops WHERE source_shop_id = $1", f"{TEST_SHOP_ID_PREFIX}002"
    )
    assert len(rows) == 1
    assert float(rows[0]["total_revenue"]) == 2000000.0


async def test_a_later_financial_year_adds_a_row_instead_of_overwriting(
    pg_conn: asyncpg.Connection,
) -> None:
    run_id = await _new_run(pg_conn)
    await sync_rows(pg_conn, run_id, [_row("003")], "FY2025-26")

    run_id_2 = await _new_run(pg_conn)
    await sync_rows(pg_conn, run_id_2, [_row("003")], "FY2026-27")

    rows = await pg_conn.fetch(
        "SELECT financial_year_id FROM sro_shops WHERE source_shop_id = $1",
        f"{TEST_SHOP_ID_PREFIX}003",
    )
    assert len(rows) == 2  # last year's snapshot is history, not overwritten


async def test_unknown_district_is_quarantined(pg_conn: asyncpg.Connection) -> None:
    run_id = await _new_run(pg_conn)
    row = _row("004", district_name="Not A Real District")

    counts = await sync_rows(pg_conn, run_id, [row], "FY2025-26")

    assert (counts.quarantined, counts.upserted) == (1, 0)
