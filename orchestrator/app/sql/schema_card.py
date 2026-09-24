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
    "license_categories": (
        "the lookup for every license_category / retail_license_category / "
        "wholesale_license_type code seen elsewhere — code, name, and kind ('wholesale', "
        "'country_liquor', 'foreign_liquor', 'composite', 'beer', 'model_shop', "
        "'premium_retail_vend'). FL2 and CL2 are kind='wholesale' — the distributor a "
        "shop's stock passes through on its way from the depot, never a retail shop's own "
        "category. A shop's own category (analytics.shops.license_category, "
        "analytics.dispatches.retail_license_category) is always one of the other kinds; "
        "analytics.dispatches.wholesale_license_type is the one column that legitimately "
        "holds FL2/CL2, for the wholesaler on that pass, not the retail shop receiving it. "
        "More than one code can share a kind — 'foreign_liquor' alone is both FL and BWFL. "
        "CL5CC is kind='country_liquor', not 'composite' — it is a Country Liquor shop with "
        "a beer endorsement, the same shop type as CL5C, never combined with foreign liquor. "
        "'composite' means only a Foreign Liquor + Beer license (FL5DB) — confirmed against "
        "~/Projects/up-excise-spatial-revenue-optimizer's own shop-type glossary, which "
        "models CL5CC as COUNTRY_LIQUOR with a hasCl5cc flag, never its own shop type. A "
        "question naming a general category ('composite', 'country liquor', 'foreign "
        "liquor', 'beer', 'model shop') rather than a specific code means every code of "
        "that kind: JOIN this view and filter on kind, never on a hand-picked code list — "
        "a memorized list silently drops whichever code you forgot it had."
    ),
    "revenues": (
        "duty/fee collections, aggregated by district + financial_year + license_category — "
        "one row per combination, not per shop and not per month. metric is 'excise_duty' | "
        "'license_fee' | 'import_fee' | 'total'; amount_inr in rupees. There is no shop_id "
        "column here; a question scoped to a specific month or to individual shops needs "
        "analytics.dispatches instead (duty_fee_inr for amount, transport_pass_issued_at "
        "for the date)."
    ),
    "sales_volumes": (
        "dispatch/consumption volumes, aggregated by district + financial_year + "
        "license_category — one row per combination, not per shop and not per month. "
        "metric is 'dispatch_bl' | 'consumption_bl' | 'cases'; quantity in the given unit. "
        "There is no shop_id or dispatch_id column here; a question scoped to a specific "
        "month or to individual shops needs analytics.dispatches instead — "
        "dispatched_bulk_litres/dispatched_cases for volume, duty_fee_inr for amount, "
        "retail_license_category for the shop type, transport_pass_issued_at for the date."
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
        "CL5CC (Country Liquor with a beer endorsement — still kind='country_liquor', not "
        "'composite'), FL4A (Model Shop), FL4C (Premium Retail Vend), FL5DB (Composite: "
        "Foreign Liquor + Beer, the only kind='composite' code). "
        "There is no separate 'beer shop' table or category — beer retail is folded "
        "into CL5CC (with country liquor) and FL5DB (with foreign liquor); filter "
        "license_category for those two codes rather than inventing a beer_shops table. "
        "See analytics.license_categories "
        "for the full code/name/kind list, including wholesale-only codes that never appear "
        "here (a shop's own license_category is never 'FL2' or 'CL2' — see that view's note)."
    ),
    "shop_years": (
        "quota/settlement per shop per financial year. mgq_bl is the minimum guaranteed quota."
    ),
    "dispatches": (
        "one row per wholesale-to-retail transport pass (a live IESCMS export, not the "
        "annual sales_volumes/revenues reconciliation, which has no shop or month "
        "granularity). Two different license-type columns exist on the same row, from the "
        "same source report: wholesale_license_type is the distributor's own code (FL2/CL2, "
        "kind='wholesale' in analytics.license_categories, never a shop's own category), and "
        "retail_license_category is the receiving shop's actual category (same codes as "
        "analytics.shops.license_category — CL5CC for country liquor with a beer "
        "endorsement, FL5DB for the separate foreign-liquor-plus-beer composite category) "
        "— a question about shop types always means retail_license_category. "
        "transport_pass_issued_at is the real business date — filter on "
        "it (not shops.created_at) for a 'how many shops in [month/year]' question; count "
        "DISTINCT shop_id, since one shop has many passes. duty_fee_inr is the amount and "
        "dispatched_bulk_litres/dispatched_cases/dispatched_bottles are the volume for a "
        "'sales in amount and volume' question scoped to a month or a shop category — this "
        "is the only view with that combination at that granularity. When the answer "
        "will show shop categories to a reader, JOIN analytics.license_categories ON "
        "code = retail_license_category and SELECT its name too — a bare code like "
        "FL4A means nothing on its own."
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
