"""Renders analytics.* into the prompt schema card handed to plan_sql, and backs the
admin data-dictionary screen's GET /schema/tables and GET /schema/tables/{name}/sample
(CLAUDE.md §Data dictionary). DATA_PIPELINE.md §Row visibility for the AI path.
"""

import asyncpg
import httpx

from app.config import settings
from app.schemas import SchemaColumn, SchemaTable

# One line of business context per view, keyed by table_name. Not every view
# needs one — a missing entry just renders without a description line.
VIEW_NOTES = {
    "districts": "75 UP districts, each under one division, each division under one zone.",
    "revenues": (
        "duty/fee collections. metric is 'excise_duty' | 'license_fee' | 'import_fee' | "
        "'total'; amount_inr in rupees."
    ),
    "sales_volumes": (
        "dispatch/consumption volumes. metric is 'dispatch_bl' | 'consumption_bl' | "
        "'cases'; quantity in the given unit."
    ),
    "operations": (
        "enforcement stats. metric is 'raids' | 'cases_registered' | 'arrests' | "
        "'liquor_seized_bl' | 'vehicles_seized'."
    ),
    "shops": (
        "one row per currently licensed shop — a present-day snapshot, not a time series. "
        "created_at/updated_at are when this row was last loaded into the database, not a "
        "business date; never filter shops by created_at/updated_at to answer a question "
        "about a specific month or year — use analytics.dispatches instead, which carries "
        "the real transport_pass_issued_at date. license_category: CL5C (Country Liquor), "
        "CL5CC (Country Liquor with Beer — a composite shop), FL4A (Model Shop), "
        "FL4C (Premium Retail Vend), FL5DB (Composite: Foreign + Country Liquor). "
        "There is no separate 'beer shop' table or category — beer retail is folded "
        "into the CL5CC and FL5DB composite categories; filter license_category for those "
        "two codes rather than inventing a beer_shops table."
    ),
    "shop_years": (
        "quota/settlement per shop per financial year. mgq_bl is the minimum guaranteed quota."
    ),
    "dispatches": (
        "one row per wholesale-to-retail transport pass (a live IESCMS export, not the "
        "annual sales_volumes reconciliation). retail_license_category is the shop's "
        "category on that pass (same codes as analytics.shops.license_category, including "
        "CL5CC/FL5DB for composite/beer). transport_pass_issued_at is the real business "
        "date — filter on it (not shops.created_at) for a 'how many shops in "
        "[month/year]' question; count DISTINCT shop_id, since one shop has many passes."
    ),
    "dispatch_strength_lines": (
        "per-strength breakdown of a country-liquor dispatch; one or more rows per "
        "analytics.dispatches row via dispatch_id. Use dispatches directly unless the "
        "question is specifically about strength_label breakdowns. This view carries no "
        "date column of its own — transport_pass_issued_at lives on analytics.dispatches "
        "only, so a strength-breakdown question that also needs a date filter (e.g. "
        "'country liquor dispatches by strength in August 2026') must JOIN dispatches ON "
        "dispatches.id = dispatch_strength_lines.dispatch_id and filter on "
        "dispatches.transport_pass_issued_at, never on dispatch_strength_lines directly."
    ),
    "brands": "registered liquor brands.",
    "brand_prices": "MRP per brand per pack size per financial year.",
    "duty_rates": "excise duty rate per licence category per financial year.",
    "policy_entries": "excise policy/circular entries with an effective date range.",
}

_SCHEMA_QUERY = """
SELECT table_name, column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_schema = 'analytics'
ORDER BY table_name, ordinal_position
"""


async def fetch_note_overrides(
    http_client: httpx.AsyncClient,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Admin-edited notes from web/'s schema_notes table (GET /api/schema-notes), split
    into table-level overrides (of VIEW_NOTES) and per-column notes (VIEW_NOTES has no
    per-column granularity of its own). web/ unset, unreachable, or empty -> no
    overrides, not an error — this is optional prompt enrichment, not required data.
    """
    if not settings.web_base_url:
        return {}, {}
    try:
        response = await http_client.get(
            f"{settings.web_base_url}/api/schema-notes",
            headers={"Authorization": f"Bearer {settings.orch_bearer_token}"},
            timeout=5,
        )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError):
        return {}, {}

    table_notes: dict[str, str] = {}
    column_notes: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["column_name"]:
            column_notes.setdefault(row["table_name"], {})[row["column_name"]] = row["note"]
        else:
            table_notes[row["table_name"]] = row["note"]
    return table_notes, column_notes


async def list_schema_tables(
    pool: asyncpg.Pool, http_client: httpx.AsyncClient
) -> list[SchemaTable]:
    table_notes, column_notes = await fetch_note_overrides(http_client)
    rows = await pool.fetch(_SCHEMA_QUERY)

    tables: dict[str, list[SchemaColumn]] = {}
    for row in rows:
        table_name = row["table_name"]
        tables.setdefault(table_name, []).append(
            SchemaColumn(
                name=row["column_name"],
                data_type=row["data_type"],
                note=column_notes.get(table_name, {}).get(row["column_name"]),
            )
        )

    return [
        SchemaTable(
            name=table_name,
            note=table_notes.get(table_name, VIEW_NOTES.get(table_name)),
            columns=columns,
        )
        for table_name, columns in sorted(tables.items())
    ]


async def sample_table(
    pool: asyncpg.Pool, table_name: str, limit: int = 5
) -> list[dict[str, str | None]]:
    """A handful of rows from one analytics.* view, for the data-dictionary screen's
    "see the data" panel. table_name must exactly match a real information_schema entry
    first — that check is what makes it safe to interpolate straight into the query
    after, since it can only ever match a table this schema genuinely has.
    """
    is_real_table = await pool.fetchval(
        "SELECT count(*) > 0 FROM information_schema.tables "
        "WHERE table_schema = 'analytics' AND table_name = $1",
        table_name,
    )
    if not is_real_table:
        raise ValueError(f"unknown table: {table_name}")

    rows = await pool.fetch(f'SELECT * FROM analytics."{table_name}" LIMIT {limit}')
    return [
        {key: str(value) if value is not None else None for key, value in r.items()} for r in rows
    ]


async def render_schema_card(pool: asyncpg.Pool, http_client: httpx.AsyncClient) -> str:
    tables = await list_schema_tables(pool, http_client)

    lines = ["Schema: analytics (the only schema you may query, SELECT only)", ""]
    for table in tables:
        header = f"analytics.{table.name}" + (f" — {table.note}" if table.note else "")
        lines.append(header)
        col_list = ", ".join(
            f"{c.name} {c.data_type}" + (f" ({c.note})" if c.note else "") for c in table.columns
        )
        lines.append(f"  {col_list}")
        lines.append("")
    return "\n".join(lines)
