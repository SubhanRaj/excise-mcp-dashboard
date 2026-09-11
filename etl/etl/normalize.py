"""District/FY/money/volume normalization. DATA_PIPELINE.md §Normalization rules —
ported as explicit rules here, not the note-row heuristic the sibling
ImportExciseData.php used to have (~/Sites/upexcise-stats-dashboard).
"""

import re
from decimal import Decimal, InvalidOperation

import asyncpg

_FY_PATTERNS = [
    re.compile(r"^(?:FY)?\s*(\d{4})[-_]\d{2}$", re.IGNORECASE),  # '2014-15', 'FY2014-15', '2014_15'
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
