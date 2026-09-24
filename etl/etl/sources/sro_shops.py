"""SRO (up-excise-spatial-revenue-optimizer, sro.exciseup.in) shop-level revenue
snapshot -> sro_shops. DATA_PIPELINE.md §SRO shop revenue snapshot.

SRO ships its own Cloudflare D1 backup as a plain SQL dump (INSERT statements
against a SQLite schema), not a live connection this app can query — the dump
file itself is the source. sqlite3 (stdlib) loads it into an in-memory
database so phase1_raw_collection can be read with a normal SELECT, the same
way any other row source here is read, with no new dependency for a one-off
text dump.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from etl import quarantine
from etl.normalize import NormalizationError, resolve_district_id

_COLLECTION_TABLE = "phase1_raw_collection"


def _valid_coord(value: float | None, *, bound: float) -> float | None:
    """A handful of real rows carry a misplaced decimal point from SRO's own
    data entry (e.g. longitude 77747738.0 instead of 77.747738) — confirmed
    against the live dump, 5 of 28,405 rows. The shop's own name and revenue
    figures on that row are still good, so this drops only the bad
    coordinate rather than quarantining the whole row over it.
    """
    if value is None or abs(value) > bound:
        return None
    return value


@dataclass(frozen=True)
class RunCounts:
    seen: int
    upserted: int
    quarantined: int


@dataclass(frozen=True)
class SroShopRow:
    district_name: str
    circle_sector_name: str
    thana_name: str
    source_shop_id: str
    shop_name: str
    shop_type: str
    has_cl5cc: bool
    latitude: float | None
    longitude: float | None
    license_fee_lf: float
    basic_license_fee_blf: float
    mgr_amount: float
    composite_lf_fl: float
    composite_lf_beer: float
    composite_mgr_fl: float
    composite_mgr_beer: float
    mgq_quantity: float
    consideration_fee: float
    special_beer_lf: float
    special_beer_mgr: float
    total_revenue: float
    uploaded_by_deo: str
    source_ref: str


def read_rows(dump_path: str) -> list[SroShopRow]:
    """Loads the whole dump into a throwaway in-memory SQLite database — the
    dump is one app's full backup (every table it has), not just the one this
    reads, so this never touches the real SRO database, only a local copy of
    its text.
    """
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(Path(dump_path).read_text(encoding="utf-8"))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM {_COLLECTION_TABLE}").fetchall()
    finally:
        conn.close()
    return [
        SroShopRow(
            district_name=r["district_name"],
            circle_sector_name=r["circle_sector_name"],
            thana_name=r["thana_name"],
            source_shop_id=str(r["shop_id"]),
            shop_name=r["shop_name"],
            shop_type=r["shop_type"],
            has_cl5cc=bool(r["has_cl5cc"]),
            latitude=_valid_coord(r["latitude_decimal"], bound=90),
            longitude=_valid_coord(r["longitude_decimal"], bound=180),
            license_fee_lf=r["license_fee_lf"] or 0,
            basic_license_fee_blf=r["basic_license_fee_blf"] or 0,
            mgr_amount=r["mgr_amount"] or 0,
            composite_lf_fl=r["composite_lf_fl"] or 0,
            composite_lf_beer=r["composite_lf_beer"] or 0,
            composite_mgr_fl=r["composite_mgr_fl"] or 0,
            composite_mgr_beer=r["composite_mgr_beer"] or 0,
            mgq_quantity=r["mgq_quantity"] or 0,
            consideration_fee=r["consideration_fee"] or 0,
            special_beer_lf=r["special_beer_lf"] or 0,
            special_beer_mgr=r["special_beer_mgr"] or 0,
            total_revenue=r["total_revenue"] or 0,
            uploaded_by_deo=r["uploaded_by_deo"],
            source_ref=f"sro:{r['id']}",
        )
        for r in rows
    ]


async def _resolve_financial_year_id(conn: asyncpg.Connection, label: str) -> int:
    fy_id = await conn.fetchval("SELECT id FROM financial_years WHERE label = $1", label)
    if fy_id is None:
        raise NormalizationError(f"no financial_years row for label={label!r}")
    return int(fy_id)


async def sync_rows(
    conn: asyncpg.Connection, run_id: int, rows: list[SroShopRow], financial_year_label: str
) -> RunCounts:
    seen = upserted = quarantined = 0
    financial_year_id = await _resolve_financial_year_id(conn, financial_year_label)

    for row in rows:
        seen += 1
        try:
            district_id = await resolve_district_id(conn, row.district_name)
        except NormalizationError as exc:
            await quarantine.record(conn, run_id, row.__dict__, str(exc))
            quarantined += 1
            continue

        await conn.execute(
            """
            INSERT INTO sro_shops
                (district_id, financial_year_id, source_shop_id, shop_name, shop_type,
                 has_cl5cc, circle_sector_name, thana_name, latitude, longitude,
                 license_fee_lf, basic_license_fee_blf, mgr_amount, composite_lf_fl,
                 composite_lf_beer, composite_mgr_fl, composite_mgr_beer, mgq_quantity,
                 consideration_fee, special_beer_lf, special_beer_mgr, total_revenue,
                 uploaded_by_deo, source_ref, published_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
                    $19,$20,$21,$22,$23,$24,now())
            ON CONFLICT (district_id, source_shop_id, financial_year_id) DO UPDATE SET
                shop_name = EXCLUDED.shop_name,
                shop_type = EXCLUDED.shop_type,
                has_cl5cc = EXCLUDED.has_cl5cc,
                circle_sector_name = EXCLUDED.circle_sector_name,
                thana_name = EXCLUDED.thana_name,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                license_fee_lf = EXCLUDED.license_fee_lf,
                basic_license_fee_blf = EXCLUDED.basic_license_fee_blf,
                mgr_amount = EXCLUDED.mgr_amount,
                composite_lf_fl = EXCLUDED.composite_lf_fl,
                composite_lf_beer = EXCLUDED.composite_lf_beer,
                composite_mgr_fl = EXCLUDED.composite_mgr_fl,
                composite_mgr_beer = EXCLUDED.composite_mgr_beer,
                mgq_quantity = EXCLUDED.mgq_quantity,
                consideration_fee = EXCLUDED.consideration_fee,
                special_beer_lf = EXCLUDED.special_beer_lf,
                special_beer_mgr = EXCLUDED.special_beer_mgr,
                total_revenue = EXCLUDED.total_revenue,
                uploaded_by_deo = EXCLUDED.uploaded_by_deo,
                source_ref = EXCLUDED.source_ref,
                published_at = COALESCE(sro_shops.published_at, now())
            """,
            district_id,
            financial_year_id,
            row.source_shop_id,
            row.shop_name,
            row.shop_type,
            row.has_cl5cc,
            row.circle_sector_name,
            row.thana_name,
            row.latitude,
            row.longitude,
            row.license_fee_lf,
            row.basic_license_fee_blf,
            row.mgr_amount,
            row.composite_lf_fl,
            row.composite_lf_beer,
            row.composite_mgr_fl,
            row.composite_mgr_beer,
            row.mgq_quantity,
            row.consideration_fee,
            row.special_beer_lf,
            row.special_beer_mgr,
            row.total_revenue,
            row.uploaded_by_deo,
            row.source_ref,
        )
        upserted += 1

    return RunCounts(seen=seen, upserted=upserted, quarantined=quarantined)


async def sync(
    conn: asyncpg.Connection, run_id: int, dump_path: str, financial_year_label: str
) -> RunCounts:
    rows = read_rows(dump_path)
    return await sync_rows(conn, run_id, rows, financial_year_label)
