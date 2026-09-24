"""Revenue / Sales Volume / Operations NITI sheets -> revenues / sales_volumes /
operations. DATA_PIPELINE.md §Source adapters: the three sheets share one
district x financial-year grain; none carries a license-category breakdown, so
every row here has `license_category_id = NULL` (the "all-category total"
case the schema already documents).

One sheet row fans out into several metric rows, one per non-blank source
column - a blank cell is skipped, never inserted as a zero (the project-wide
0-vs-blank rule, DATA_PIPELINE.md's own §Normalization rules and CLAUDE.md's
Mentor-DB notes: 0 is a real value, a blank means "not collected").

revenues.metric and sales_volumes.metric are plain TEXT (the schema comment's
'excise_duty' | 'license_fee' | ... list is illustrative, not an enum - the
real sheets have far more granular columns than that list names), so the
metric slugs below are named after the actual source columns rather than
forced into a shorter list that doesn't fit them.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

import asyncpg
import openpyxl

from etl import quarantine
from etl.normalize import (
    NormalizationError,
    normalize_money,
    parse_financial_year,
    resolve_district_id,
    seed_district_aliases,
)


@dataclass(frozen=True)
class RunCounts:
    seen: int
    upserted: int
    quarantined: int


@dataclass(frozen=True)
class FactRow:
    district_name: str
    financial_year_raw: str
    metric: str
    value: Decimal
    unit: str | None
    source_ref: str


REVENUE_SHEET = "2. Revenue"
SALES_VOLUME_SHEET = "3. Sales Volume"
OPERATIONS_SHEET = "4. Operations"

# column index (0-based, header row is index 0) -> metric slug. Column 0 is
# District, column 1 is Financial year on every one of these three sheets.
_REVENUE_METRICS: dict[int, str] = {
    2: "excise_duty",
    3: "additional_excise_duty",
    4: "license_fee_annual",
    5: "license_fee_auction_lottery",
    6: "permit_pass_fee",
    7: "label_brand_registration_fee",
    8: "bottling_fee",
    9: "import_export_fee",
    10: "penalties_fines",
    11: "vat_sales_tax",
    12: "other_receipt",
    # 13 is the free-text "what was it" note, 14 is the live TOTAL formula -
    # neither is a revenue figure of its own, both skipped.
}

_SALES_VOLUME_METRICS: dict[int, str] = {
    3: "country_liquor_upml",
    4: "country_liquor_cml",
    5: "imfl",
    6: "imfl_premium",  # a subset of column 5's IMFL, not additional volume
    7: "beer",
    8: "wine",
    9: "imported_liquor",
    10: "rtd_low_alcohol",
    # 11 is the live TOTAL formula, skipped.
}

# Operations has no per-drink-type breakdown and no unit column on the
# `operations` table itself (schema: district_id, financial_year_id, metric,
# value - no unit), so every column becomes its own metric with the unit
# folded into the metric name only where the source unit actually varies
# (column 7, dispatch quantity, paired with column 8's unit).
_OPERATIONS_COUNT_METRICS: dict[int, str] = {
    2: "wholesale_licences",
    3: "retail_shops",
    4: "composite_shops",
    5: "model_shops",
    6: "other_outlets",
    9: "inspections_raids",
    10: "firs_registered",
    11: "illicit_liquor_seized_litres",
    12: "cases_prosecuted",
    13: "convictions",
    14: "shop_closure_days_covid",
    15: "shop_closure_days_elections",
    16: "deaths_illicit_liquor",
    17: "hospital_admissions",
    18: "lab_samples_tested",
    19: "lab_samples_failed",
}


def _coerce_number(value: object) -> Decimal | None:
    if value is None or value == "" or (isinstance(value, str) and value.strip() == "-"):
        return None  # '-' is this project's own "not collected" placeholder, same as blank
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        # A handful of cells hold something that isn't a number at all even after
        # stripping currency/commas (CLAUDE.md's "Comma formatting" caveat) - treated
        # as not-collected (None), same as a blank cell, rather than guessed.
        try:
            return normalize_money(value)
        except NormalizationError:
            return None
    raise NormalizationError(f"unexpected cell type for a numeric column: {value!r}")


def _load_rows(path: str, sheet_name: str) -> Iterator[tuple[int, tuple[object, ...]]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[sheet_name]
    for i, row in enumerate(sheet.iter_rows(values_only=True)):
        if i == 0 or row[0] is None:
            continue  # header, or a trailing blank/note line
        yield i, row
    workbook.close()


def read_revenue_rows(path: str) -> Iterator[FactRow]:
    for i, row in _load_rows(path, REVENUE_SHEET):
        for col, metric in _REVENUE_METRICS.items():
            value = _coerce_number(row[col])
            if value is None:
                continue
            yield FactRow(
                district_name=str(row[0]).strip(),
                financial_year_raw=str(row[1]).strip(),
                metric=metric,
                value=value,
                unit=None,
                source_ref=f"niti_revenue:{path}:{i}:{metric}",
            )


def read_sales_volume_rows(path: str) -> Iterator[FactRow]:
    for i, row in _load_rows(path, SALES_VOLUME_SHEET):
        unit = str(row[2]).strip() if row[2] else None
        for col, metric in _SALES_VOLUME_METRICS.items():
            value = _coerce_number(row[col])
            if value is None:
                continue
            yield FactRow(
                district_name=str(row[0]).strip(),
                financial_year_raw=str(row[1]).strip(),
                metric=metric,
                value=value,
                unit=unit,
                source_ref=f"niti_sales_volume:{path}:{i}:{metric}",
            )


def read_operations_rows(path: str) -> Iterator[FactRow]:
    for i, row in _load_rows(path, OPERATIONS_SHEET):
        district_name = str(row[0]).strip()
        fy_raw = str(row[1]).strip()
        for col, metric in _OPERATIONS_COUNT_METRICS.items():
            value = _coerce_number(row[col])
            if value is None:
                continue
            yield FactRow(
                district_name=district_name,
                financial_year_raw=fy_raw,
                metric=metric,
                value=value,
                unit=None,
                source_ref=f"niti_operations:{path}:{i}:{metric}",
            )
        dispatch_qty = _coerce_number(row[7])
        if dispatch_qty is not None:
            dispatch_unit = str(row[8]).strip().lower() if row[8] else ""
            is_volume = dispatch_unit in ("bulk litres", "bl", "l", "kl")
            metric = "dispatch_bl" if is_volume else "dispatch_cases"
            yield FactRow(
                district_name=district_name,
                financial_year_raw=fy_raw,
                metric=metric,
                value=dispatch_qty,
                unit=None,
                source_ref=f"niti_operations:{path}:{i}:{metric}",
            )


async def _resolve_financial_year_id(
    conn: asyncpg.Connection, cache: dict[str, int], raw: str
) -> int:
    if raw in cache:
        return cache[raw]
    start_year = parse_financial_year(raw)
    fy_id = await conn.fetchval("SELECT id FROM financial_years WHERE start_year = $1", start_year)
    if fy_id is None:
        raise NormalizationError(f"no financial_years row for start_year={start_year}")
    cache[raw] = int(fy_id)
    return cache[raw]


async def _resolve_district(conn: asyncpg.Connection, cache: dict[str, int], name: str) -> int:
    if name in cache:
        return cache[name]
    district_id = await resolve_district_id(conn, name)
    cache[name] = district_id
    return district_id


async def _upsert_revenue_or_sales(
    conn: asyncpg.Connection,
    *,
    table: str,
    value_col: str,
    district_id: int,
    financial_year_id: int,
    metric: str,
    value: Decimal,
    unit: str | None,
    source_ref: str,
) -> None:
    # Manual check-then-write instead of INSERT ... ON CONFLICT: both tables'
    # natural key includes license_category_id, which is always NULL for this
    # source (no per-category breakdown exists in Revenue/Sales Volume), and
    # Postgres never treats two NULLs as conflicting under a UNIQUE constraint
    # - an ON CONFLICT arbiter on that key would silently never fire and every
    # re-run would insert a fresh duplicate row instead of updating in place
    # (loader.py's NATURAL_KEYS comment flags this exact gap; this is it).
    if table == "sales_volumes" and unit is None:
        raise NormalizationError("sales_volumes.unit is required but the source cell was blank")

    existing_id = await conn.fetchval(
        f"SELECT id FROM {table} WHERE district_id = $1 AND financial_year_id = $2 "
        f"AND license_category_id IS NULL AND metric = $3",
        district_id,
        financial_year_id,
        metric,
    )
    if unit is None:
        if existing_id is None:
            await conn.execute(
                f"INSERT INTO {table} (district_id, financial_year_id, license_category_id, "
                f"metric, {value_col}, published_at, source_ref) "
                f"VALUES ($1, $2, NULL, $3, $4, now(), $5)",
                district_id,
                financial_year_id,
                metric,
                value,
                source_ref,
            )
        else:
            await conn.execute(
                f"UPDATE {table} SET {value_col} = $1, source_ref = $2, updated_at = now() "
                f"WHERE id = $3",
                value,
                source_ref,
                existing_id,
            )
    else:
        if existing_id is None:
            await conn.execute(
                f"INSERT INTO {table} (district_id, financial_year_id, license_category_id, "
                f"metric, {value_col}, unit, published_at, source_ref) "
                f"VALUES ($1, $2, NULL, $3, $4, $5, now(), $6)",
                district_id,
                financial_year_id,
                metric,
                value,
                unit,
                source_ref,
            )
        else:
            await conn.execute(
                f"UPDATE {table} SET {value_col} = $1, unit = $2, "
                f"source_ref = $3, updated_at = now() WHERE id = $4",
                value,
                unit,
                source_ref,
                existing_id,
            )


async def sync_revenue_or_sales_rows(
    conn: asyncpg.Connection, run_id: int, table: str, value_col: str, rows: list[FactRow]
) -> RunCounts:
    seen = upserted = quarantined = 0
    district_cache: dict[str, int] = {}
    fy_cache: dict[str, int] = {}
    for row in rows:
        seen += 1
        try:
            district_id = await _resolve_district(conn, district_cache, row.district_name)
            fy_id = await _resolve_financial_year_id(conn, fy_cache, row.financial_year_raw)
            await _upsert_revenue_or_sales(
                conn,
                table=table,
                value_col=value_col,
                district_id=district_id,
                financial_year_id=fy_id,
                metric=row.metric,
                value=row.value,
                unit=row.unit,
                source_ref=row.source_ref,
            )
        except NormalizationError as exc:
            await quarantine.record(conn, run_id, row.__dict__, str(exc))
            quarantined += 1
            continue
        upserted += 1
    return RunCounts(seen=seen, upserted=upserted, quarantined=quarantined)


async def sync_operations_rows(
    conn: asyncpg.Connection, run_id: int, rows: list[FactRow]
) -> RunCounts:
    seen = upserted = quarantined = 0
    district_cache: dict[str, int] = {}
    fy_cache: dict[str, int] = {}
    for row in rows:
        seen += 1
        try:
            district_id = await _resolve_district(conn, district_cache, row.district_name)
            fy_id = await _resolve_financial_year_id(conn, fy_cache, row.financial_year_raw)
        except NormalizationError as exc:
            await quarantine.record(conn, run_id, row.__dict__, str(exc))
            quarantined += 1
            continue
        # operations' natural key (district_id, financial_year_id, metric) has
        # no nullable column, so the plain ON CONFLICT upsert is safe here.
        await conn.execute(
            """
            INSERT INTO operations
                (district_id, financial_year_id, metric, value, published_at, source_ref)
            VALUES ($1, $2, $3, $4, now(), $5)
            ON CONFLICT (district_id, financial_year_id, metric) DO UPDATE SET
                value = EXCLUDED.value, source_ref = EXCLUDED.source_ref, updated_at = now()
            """,
            district_id,
            fy_id,
            row.metric,
            row.value,
            row.source_ref,
        )
        upserted += 1
    return RunCounts(seen=seen, upserted=upserted, quarantined=quarantined)


async def sync(conn: asyncpg.Connection, run_id: int, path: str, kind: str) -> RunCounts:
    await seed_district_aliases(conn)
    if kind == "revenue":
        return await sync_revenue_or_sales_rows(
            conn, run_id, "revenues", "amount_inr", list(read_revenue_rows(path))
        )
    if kind == "sales_volume":
        return await sync_revenue_or_sales_rows(
            conn, run_id, "sales_volumes", "quantity", list(read_sales_volume_rows(path))
        )
    if kind == "operations":
        return await sync_operations_rows(conn, run_id, list(read_operations_rows(path)))
    raise ValueError(f"unknown niti_facts kind: {kind!r}")
