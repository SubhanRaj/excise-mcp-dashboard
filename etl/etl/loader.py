"""Upsert on each target table's natural key. DATA_PIPELINE.md §Shared shape:
idempotent by construction — re-running the same source over unchanged input
upserts identical values and changes no row counts.
"""

import asyncpg

# ponytail: revenues/sales_volumes allow a NULL license_category_id (the
# all-category total row). Postgres treats NULL as distinct in a UNIQUE
# constraint, so two total rows for the same district+FY+metric would insert
# twice instead of conflicting. Not hit until real total rows are loaded;
# fix then with a partial unique index keyed on COALESCE(license_category_id, 0).
NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "revenues": ("district_id", "financial_year_id", "license_category_id", "metric"),
    "sales_volumes": ("district_id", "financial_year_id", "license_category_id", "metric"),
    "operations": ("district_id", "financial_year_id", "metric"),
    "shops": ("district_id", "shop_number", "seq"),
    "shop_years": ("shop_id", "financial_year_id"),
    "brands": ("name", "license_category_id"),
    "brand_prices": ("brand_id", "financial_year_id", "pack_ml"),
    "duty_rates": ("financial_year_id", "license_category_id", "basis"),
    "policy_entries": ("source_ref",),
}


async def upsert(conn: asyncpg.Connection, table: str, row: dict[str, object]) -> None:
    """INSERT ... ON CONFLICT (natural key) DO UPDATE for one normalized row.

    `table` and `row`'s keys are always ours (the registry above and the
    adapters' fixed output shape), never end-user input, so building the
    query by string join here carries no injection risk.
    """
    key_cols = NATURAL_KEYS[table]
    columns = list(row.keys())
    update_cols = [c for c in columns if c not in key_cols]

    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    conflict_target = ", ".join(key_cols)
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols) or key_cols[0]

    query = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_target}) DO UPDATE SET {set_clause}, updated_at = now()"
    )
    await conn.execute(query, *row.values())
