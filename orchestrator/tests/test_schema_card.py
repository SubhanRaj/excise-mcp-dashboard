"""sql/schema_card.py against a fake pool (no live Postgres needed)."""

from app.sql.schema_card import render_schema_card


class _FakePool:
    async def fetch(self, query: str) -> list[dict[str, object]]:
        return [
            {"table_name": "districts", "column_name": "id", "data_type": "bigint"},
            {"table_name": "districts", "column_name": "name", "data_type": "citext"},
            {"table_name": "revenues", "column_name": "amount_inr", "data_type": "numeric"},
        ]


async def test_render_schema_card_groups_by_table() -> None:
    card = await render_schema_card(_FakePool())  # type: ignore[arg-type]
    assert "analytics.districts" in card
    assert "id bigint" in card
    assert "name citext" in card
    assert "analytics.revenues" in card
    assert "75 UP districts" in card  # VIEW_NOTES entry rendered in
