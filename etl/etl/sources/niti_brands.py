"""Brands / Brand Prices NITI sheets -> brands / brand_prices.
DATA_PIPELINE.md §Source adapters. Brands must sync before Brand Prices -
`sync()` below does both in that order since brand_prices.brand_id resolves
against the brands rows this same run just wrote.

Neither sheet carries one of the twelve seeded license_categories codes
directly - "Type of drink" is IMFL / Beer / Country liquor / Wine / Imported
liquor / blank. Three of those six have an unambiguous `kind` in
license_categories (IMFL -> FL, Beer -> BEER, Country liquor -> CL); Wine and
Imported liquor have no matching `kind` at all (no wine/imported kind was ever
seeded) and a blank has nothing to map. All three load with
`license_category_id = NULL` - the brand itself is still real data, just
uncategorized, never guessed onto a code that doesn't fit.

brand_prices has two price columns (mrp_inr, ex_distillery_inr) against the
source's four (declared by manufacturer, approved by department, MRP, excise
duty per case). MRP maps directly. "Approved by the department" is the
figure actually in force (declared is only the manufacturer's opening ask,
which the department can override) and is what `ex_distillery_inr` means in
this domain, so that's what fills it. "Declared by manufacturer" and "excise
duty charged" have no column here and are not loaded - noted in the run
summary, not silently dropped.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import asyncpg
import openpyxl

from etl import quarantine
from etl.normalize import NormalizationError, parse_financial_year

BRANDS_SHEET = "6. Brands"
BRAND_PRICES_SHEET = "7. Brand Prices"

# "Type of drink" (Brands sheet) -> the one license_categories.code it means.
# None = no seeded kind covers this drink type, or the cell was blank.
_DRINK_TYPE_TO_CODE: dict[str, str | None] = {
    "IMFL": "FL",
    "Beer": "BEER",
    "Country liquor": "CL",
    "Wine": None,
    "Imported liquor": None,
}


@dataclass(frozen=True)
class RunCounts:
    seen: int
    upserted: int
    quarantined: int


@dataclass(frozen=True)
class BrandRow:
    name: str
    manufacturer: str | None
    drink_type_raw: str | None
    is_premium: bool | None
    source_ref: str


@dataclass(frozen=True)
class BrandPriceRow:
    brand_name: str
    pack_ml: int
    financial_year_raw: str
    mrp_inr: Decimal | None
    ex_distillery_inr: Decimal | None
    source_ref: str


def _num(value: object) -> Decimal | None:
    if value is None or value == "" or (isinstance(value, str) and value.strip() == "-"):
        return None  # '-' is this project's own "not collected" placeholder, same as blank
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip().replace(",", ""))
        except InvalidOperation:
            return None
    raise NormalizationError(f"unexpected cell type for a numeric column: {value!r}")


def _yesno(value: object) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return True if text == "yes" else False if text == "no" else None


def read_brand_rows(path: str) -> Iterator[BrandRow]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[BRANDS_SHEET]
    rows = sheet.iter_rows(values_only=True)
    next(rows)
    for i, r in enumerate(rows, start=2):
        if r[0] is None:
            continue
        yield BrandRow(
            name=str(r[0]).strip(),
            manufacturer=str(r[1]).strip() if r[1] else None,
            drink_type_raw=str(r[2]).strip() if r[2] else None,
            is_premium=_yesno(r[6]),
            source_ref=f"niti_brands:{path}:{i}",
        )
    workbook.close()


def read_brand_price_rows(path: str) -> Iterator[BrandPriceRow]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[BRAND_PRICES_SHEET]
    rows = sheet.iter_rows(values_only=True)
    next(rows)
    for i, r in enumerate(rows, start=2):
        if r[0] is None:
            continue
        pack_ml = r[1]
        if not isinstance(pack_ml, int | float):
            continue  # unparseable pack size - can't form the natural key, skip rather than guess
        yield BrandPriceRow(
            brand_name=str(r[0]).strip(),
            pack_ml=int(pack_ml),
            financial_year_raw=str(r[3]).strip() if r[3] else "",
            mrp_inr=_num(r[8]),
            ex_distillery_inr=_num(r[5]),
            source_ref=f"niti_brand_prices:{path}:{i}",
        )
    workbook.close()


async def _upsert_brand(
    conn: asyncpg.Connection,
    *,
    name: str,
    manufacturer: str | None,
    license_category_id: int | None,
    segment: str | None,
) -> int:
    # Manual check-then-write, not ON CONFLICT: brands' natural key (name,
    # license_category_id) has a nullable column, and most brands here resolve
    # to license_category_id = NULL (see module docstring) - the same
    # NULL-never-conflicts gap as revenues/sales_volumes (niti_facts.py).
    existing_id = await conn.fetchval(
        "SELECT id FROM brands WHERE name = $1 AND license_category_id IS NOT DISTINCT FROM $2",
        name,
        license_category_id,
    )
    if existing_id is not None:
        await conn.execute(
            "UPDATE brands SET manufacturer = $1, segment = $2, "
            "published_at = COALESCE(published_at, now()), updated_at = now() WHERE id = $3",
            manufacturer,
            segment,
            existing_id,
        )
        return int(existing_id)
    return int(
        await conn.fetchval(
            """
            INSERT INTO brands (name, license_category_id, segment, manufacturer, published_at)
            VALUES ($1, $2, $3, $4, now())
            RETURNING id
            """,
            name,
            license_category_id,
            segment,
            manufacturer,
        )
    )


async def sync_brand_rows(conn: asyncpg.Connection, run_id: int, rows: list[BrandRow]) -> RunCounts:
    seen = upserted = quarantined = 0
    for row in rows:
        seen += 1
        code = _DRINK_TYPE_TO_CODE.get(row.drink_type_raw or "")
        license_category_id = None
        if code is not None:
            license_category_id = await conn.fetchval(
                "SELECT id FROM license_categories WHERE code = $1", code
            )
        segment = "premium" if row.is_premium else "regular" if row.is_premium is False else None
        await _upsert_brand(
            conn,
            name=row.name,
            manufacturer=row.manufacturer,
            license_category_id=license_category_id,
            segment=segment,
        )
        upserted += 1
    return RunCounts(seen=seen, upserted=upserted, quarantined=quarantined)


async def _resolve_brand_id(
    conn: asyncpg.Connection, cache: dict[str, int | None], name: str
) -> int:
    if name in cache:
        cached = cache[name]
        if cached is None:
            raise NormalizationError(f"unknown brand: {name!r}")
        return cached
    matches = await conn.fetch("SELECT id FROM brands WHERE name = $1", name)
    if len(matches) == 0:
        cache[name] = None
        raise NormalizationError(f"unknown brand: {name!r}")
    if len(matches) > 1:
        cache[name] = None
        raise NormalizationError(
            f"ambiguous brand name, {len(matches)} category variants exist: {name!r}"
        )
    resolved_id = int(matches[0]["id"])
    cache[name] = resolved_id
    return resolved_id


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


def _dedupe_or_flag_conflicts(
    rows: list[BrandPriceRow],
) -> tuple[list[BrandPriceRow], list[BrandPriceRow]]:
    """Groups by the natural key before any resolves-to-id has happened. An
    exact-duplicate group collapses to one row; a group whose price figures
    genuinely disagree is returned separately for quarantine rather than
    letting a plain upsert let the last one silently win (7_Brand_Prices.xlsx
    is known to still carry some unresolved price conflicts, CLAUDE.md
    "Revisit the 55 conflicting-price-value rows").
    """
    groups: dict[tuple[str, int, str], list[BrandPriceRow]] = {}
    for row in rows:
        key = (row.brand_name.lower(), row.pack_ml, row.financial_year_raw)
        groups.setdefault(key, []).append(row)

    clean: list[BrandPriceRow] = []
    conflicted: list[BrandPriceRow] = []
    for group in groups.values():
        distinct_values = {(r.mrp_inr, r.ex_distillery_inr) for r in group}
        if len(distinct_values) == 1:
            clean.append(group[0])
        else:
            conflicted.extend(group)
    return clean, conflicted


async def sync_brand_price_rows(
    conn: asyncpg.Connection, run_id: int, rows: list[BrandPriceRow]
) -> RunCounts:
    seen = len(rows)
    upserted = quarantined = 0
    clean_rows, conflicted_rows = _dedupe_or_flag_conflicts(rows)

    for row in conflicted_rows:
        await quarantine.record(
            conn,
            run_id,
            row.__dict__,
            "conflicting price figures for the same brand/pack/financial-year (unresolved "
            "source duplicate, CLAUDE.md 'Revisit the 55 conflicting-price-value rows')",
        )
        quarantined += 1

    brand_cache: dict[str, int | None] = {}
    fy_cache: dict[str, int] = {}
    for row in clean_rows:
        try:
            brand_id = await _resolve_brand_id(conn, brand_cache, row.brand_name)
            fy_id = await _resolve_financial_year_id(conn, fy_cache, row.financial_year_raw)
            if row.mrp_inr is None:
                raise NormalizationError("mrp_inr is required but the source cell was blank")
        except NormalizationError as exc:
            await quarantine.record(conn, run_id, row.__dict__, str(exc))
            quarantined += 1
            continue
        await conn.execute(
            """
            INSERT INTO brand_prices (brand_id, financial_year_id, pack_ml, mrp_inr,
                                       ex_distillery_inr, published_at)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (brand_id, financial_year_id, pack_ml) DO UPDATE SET
                mrp_inr = EXCLUDED.mrp_inr, ex_distillery_inr = EXCLUDED.ex_distillery_inr,
                updated_at = now()
            """,
            brand_id,
            fy_id,
            row.pack_ml,
            row.mrp_inr,
            row.ex_distillery_inr,
        )
        upserted += 1

    return RunCounts(seen=seen, upserted=upserted, quarantined=quarantined)


async def sync(conn: asyncpg.Connection, run_id: int, path: str, kind: str) -> RunCounts:
    if kind == "brands":
        return await sync_brand_rows(conn, run_id, list(read_brand_rows(path)))
    if kind == "brand_prices":
        return await sync_brand_price_rows(conn, run_id, list(read_brand_price_rows(path)))
    raise ValueError(f"unknown niti_brands kind: {kind!r}")
