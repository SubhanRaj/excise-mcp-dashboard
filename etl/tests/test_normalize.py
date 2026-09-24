from decimal import Decimal

import asyncpg
import pytest

from etl.config import settings
from etl.normalize import (
    NITI_DISTRICT_ALIASES,
    NormalizationError,
    normalize_money,
    normalize_volume_bl,
    parse_financial_year,
    resolve_district_id,
    seed_district_aliases,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2014-15", 2014),
        ("FY2014-15", 2014),
        ("2014_15", 2014),
        ("2014", 2014),
        ("2014-2015", 2014),  # the Shops / Brand Prices sheets' 4-digit-4-digit form
        ("FY2014-2015", 2014),
        ("2024.25", 2024),  # Shahjahanpur's Shops sheet: a dot instead of a hyphen
        ("2017--18", 2017),  # Jaunpur's Shops sheet: a doubled hyphen
    ],
)
def test_parse_financial_year_accepts_known_formats(raw: str, expected: int) -> None:
    assert parse_financial_year(raw) == expected


def test_parse_financial_year_rejects_garbage() -> None:
    with pytest.raises(NormalizationError):
        parse_financial_year("not a year")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("₹1,23,456.00", Decimal("123456.00")), ("1000", Decimal("1000")), (" 500 ", Decimal("500"))],
)
def test_normalize_money_strips_currency_formatting(raw: str, expected: Decimal) -> None:
    assert normalize_money(raw) == expected


def test_normalize_money_rejects_non_numeric() -> None:
    with pytest.raises(NormalizationError):
        normalize_money("not a number")


def test_normalize_volume_bl_converts_kilolitres() -> None:
    assert normalize_volume_bl("2", "KL") == Decimal("2000")


def test_normalize_volume_bl_rejects_unknown_unit() -> None:
    with pytest.raises(NormalizationError):
        normalize_volume_bl("10", "gallons")


async def test_seed_district_aliases_resolves_niti_spelling_variants() -> None:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        await seed_district_aliases(conn)
        prayagraj_id = await conn.fetchval("SELECT id FROM districts WHERE name = 'Prayagraj'")
        resolved = await resolve_district_id(conn, "Allahabad (Prayagraj)")
        assert resolved == prayagraj_id
        # idempotent: seeding twice doesn't error or change the mapping
        await seed_district_aliases(conn)
        assert await resolve_district_id(conn, "Allahabad (Prayagraj)") == prayagraj_id
    finally:
        await conn.execute(
            "DELETE FROM etl.district_aliases WHERE alias = ANY($1)",
            list(NITI_DISTRICT_ALIASES),
        )
        await conn.close()
