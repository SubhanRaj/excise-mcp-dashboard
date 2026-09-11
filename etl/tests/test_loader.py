"""loader.upsert builds its SQL from a fixed registry + a row's own keys, so this
checks the query shape without a live database — the ON CONFLICT DO UPDATE
behavior itself is exercised against a real Postgres once excise_bank exists
(ROADMAP.md Milestone 1's outstanding "verify excise_ro is read-only" step
covers the sibling read-only-role check; a live-DB loader test is the
natural-key equivalent, added once `etl/.env` points at a real database).
"""

from unittest.mock import AsyncMock

import pytest

from etl.loader import NATURAL_KEYS, upsert


@pytest.mark.asyncio
async def test_upsert_conflicts_on_the_table_natural_key() -> None:
    conn = AsyncMock()
    row = {
        "district_id": 1,
        "financial_year_id": 2,
        "metric": "raids",
        "value": 5,
        "source_ref": "csv:test:1",
    }
    await upsert(conn, "operations", row)

    query = conn.execute.call_args.args[0]
    assert "INSERT INTO operations" in query
    assert "ON CONFLICT (district_id, financial_year_id, metric) DO UPDATE" in query
    assert "value = EXCLUDED.value" in query
    assert "district_id = EXCLUDED.district_id" not in query  # key columns are never re-set


def test_every_target_table_has_a_natural_key() -> None:
    for table in (
        "revenues",
        "sales_volumes",
        "operations",
        "shops",
        "shop_years",
        "brands",
        "brand_prices",
        "duty_rates",
        "policy_entries",
    ):
        assert NATURAL_KEYS[table]
