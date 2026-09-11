"""Renders analytics.* into the prompt schema card handed to plan_sql.
DATA_PIPELINE.md §Row visibility for the AI path.
"""

import asyncpg

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
    "shops": "one row per licensed shop.",
    "shop_years": (
        "quota/settlement per shop per financial year. mgq_bl is the minimum guaranteed quota."
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


async def render_schema_card(pool: asyncpg.Pool) -> str:
    rows = await pool.fetch(_SCHEMA_QUERY)
    tables: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        tables.setdefault(row["table_name"], []).append((row["column_name"], row["data_type"]))

    lines = ["Schema: analytics (the only schema you may query, SELECT only)", ""]
    for table_name, columns in sorted(tables.items()):
        note = VIEW_NOTES.get(table_name)
        header = f"analytics.{table_name}" + (f" — {note}" if note else "")
        lines.append(header)
        col_list = ", ".join(f"{name} {dtype}" for name, dtype in columns)
        lines.append(f"  {col_list}")
        lines.append("")
    return "\n".join(lines)
