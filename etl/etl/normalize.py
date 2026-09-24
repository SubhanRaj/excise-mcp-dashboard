"""District/FY/money/volume normalization. DATA_PIPELINE.md §Normalization rules —
ported as explicit rules here, not the note-row heuristic the sibling
ImportExciseData.php used to have (~/Sites/upexcise-stats-dashboard).
"""

import re
from decimal import Decimal, InvalidOperation

import asyncpg

_FY_PATTERNS = [
    # '2014-15', 'FY2014-15', '2014_15', '2024.25' (Shahjahanpur), '2017--18'
    # (Jaunpur, a doubled separator) - one or more of -/_/. between the two years.
    re.compile(r"^(?:FY)?\s*(\d{4})[-_.]+\d{2}$", re.IGNORECASE),
    # '2014-2015' (Shops, Brand Prices)
    re.compile(r"^(?:FY)?\s*(\d{4})[-_.]+\d{4}$", re.IGNORECASE),
    re.compile(r"^(\d{4})$"),  # '2014'
]

_MONEY_STRIP = re.compile(r"[₹,\s]")

_VOLUME_UNITS_TO_BL = {
    "BL": Decimal(1),
    "L": Decimal(1),
    "KL": Decimal(1000),
}


class NormalizationError(ValueError):
    """Raised for a value that fails a normalization rule; the caller quarantines
    the row with this exception's message as `reason`.
    """


def parse_financial_year(raw: str) -> int:
    """'2014-15' / 'FY2014-15' / '2014_15' / '2014' -> financial_years.start_year (2014)."""
    value = raw.strip()
    for pattern in _FY_PATTERNS:
        if match := pattern.match(value):
            return int(match.group(1))
    raise NormalizationError(f"unparseable financial year: {raw!r}")


def normalize_money(raw: str) -> Decimal:
    """Strip ₹/commas/spaces, store rupees (not lakh/crore) — the caller decides
    the input unit and multiplies before this if the source isn't already rupees.
    """
    cleaned = _MONEY_STRIP.sub("", raw)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise NormalizationError(f"unparseable money value: {raw!r}") from exc


def normalize_volume_bl(quantity: str, unit: str) -> Decimal:
    """Convert a quantity to bulk litres (BL); 'cases' stays its own metric,
    never converted here.
    """
    factor = _VOLUME_UNITS_TO_BL.get(unit.strip().upper())
    if factor is None:
        raise NormalizationError(f"unknown volume unit: {unit!r}")
    try:
        return Decimal(quantity.strip()) * factor
    except InvalidOperation as exc:
        raise NormalizationError(f"unparseable volume value: {quantity!r}") from exc


# Spelling/format variants the NITI workbooks use that don't match
# `districts.name` exactly (parenthetical old names, space/no-space variants,
# a bare short form) -> the canonical name already seeded in `districts`.
# Seeded into `etl.district_aliases` once per run by `seed_district_aliases`
# below; `resolve_district_id` then finds them the same way as any other
# alias, no separate lookup path needed.
NITI_DISTRICT_ALIASES: dict[str, str] = {
    "Allahabad (Prayagraj)": "Prayagraj",
    "Ayodhya (Faizabad)": "Ayodhya",
    "Rae Bareli": "Raebareli",
    "Sant Ravidas Nagar (Bhadohi)": "Bhadohi",
    "Sant Ravidas Nagar Bhadohi": "Bhadohi",
    "Siddharth Nagar": "Siddharthnagar",
    "Bara Banki": "Barabanki",
    "Bulandshahar": "Bulandshahr",
    "Kheri": "Lakhimpur Kheri",  # the Shops workbook's Lakhimpur Kheri sheet uses this short form
    "Mahrajganj": "Maharajganj",  # the Shops workbook's sheet name, missing the second "a"
    "Shrawasti": "Shravasti",  # the Shops workbook's sheet name, "w" instead of "v"
}


async def seed_district_aliases(conn: asyncpg.Connection) -> None:
    """Idempotent: inserts each NITI_DISTRICT_ALIASES entry once, resolving the
    canonical name against `districts` at insert time. A no-op on a re-run.
    """
    for alias, canonical_name in NITI_DISTRICT_ALIASES.items():
        await conn.execute(
            """
            INSERT INTO etl.district_aliases (alias, district_id)
            SELECT $1, id FROM districts WHERE name = $2
            ON CONFLICT (alias) DO NOTHING
            """,
            alias,
            canonical_name,
        )


async def resolve_district_id(conn: asyncpg.Connection, name: str) -> int:
    """Resolve a district name against `districts`, falling back to the alias
    table for known spelling variants. Raises if neither resolves — the caller
    quarantines with `reason = 'unknown district: <value>'`.
    """
    district_id = await conn.fetchval("SELECT id FROM districts WHERE name = $1", name)
    if district_id is None:
        district_id = await conn.fetchval(
            "SELECT district_id FROM etl.district_aliases WHERE alias = $1", name
        )
    if district_id is None:
        raise NormalizationError(f"unknown district: {name!r}")
    return int(district_id)
