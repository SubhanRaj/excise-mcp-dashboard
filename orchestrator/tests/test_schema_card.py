"""sql/schema_card.py against a fake pool and a fake http client (no live Postgres or
web/ needed).
"""

import httpx
import pytest

from app.sql import schema_card
from app.sql.schema_card import (
    fetch_note_overrides,
    list_schema_tables,
    render_schema_card,
    sample_table,
)


class _FakePool:
    def __init__(self, table_exists: bool = True) -> None:
        self._table_exists = table_exists

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if "information_schema.columns" in query:
            return [
                {"table_name": "districts", "column_name": "id", "data_type": "bigint"},
                {"table_name": "districts", "column_name": "name", "data_type": "citext"},
                {"table_name": "revenues", "column_name": "amount_inr", "data_type": "numeric"},
            ]
        return [{"id": 1, "amount_inr": None}]

    async def fetchval(self, query: str, *args: object) -> bool:
        return self._table_exists


class _FakeResponse:
    def __init__(self, payload: list[dict[str, str]]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> list[dict[str, str]]:
        return self._payload


class _FakeHttpClient:
    def __init__(
        self, payload: list[dict[str, str]] | None = None, raise_error: bool = False
    ) -> None:
        self._payload = payload or []
        self._raise_error = raise_error

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        if self._raise_error:
            raise httpx.ConnectError("unreachable")
        return _FakeResponse(self._payload)


async def test_render_schema_card_groups_by_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_card.settings, "web_base_url", "")
    card = await render_schema_card(_FakePool(), _FakeHttpClient())  # type: ignore[arg-type]
    assert "analytics.districts" in card
    assert "id bigint" in card
    assert "name citext" in card
    assert "analytics.revenues" in card
    assert "75 UP districts" in card  # VIEW_NOTES entry rendered in


async def test_fetch_note_overrides_disabled_when_web_base_url_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schema_card.settings, "web_base_url", "")
    client = _FakeHttpClient(payload=[{"table_name": "districts", "column_name": "", "note": "x"}])

    table_notes, column_notes = await fetch_note_overrides(client)  # type: ignore[arg-type]

    assert table_notes == {}
    assert column_notes == {}


async def test_fetch_note_overrides_splits_table_and_column_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schema_card.settings, "web_base_url", "http://web.local")
    payload = [
        {"table_name": "districts", "column_name": "", "note": "an admin's own table note"},
        {"table_name": "districts", "column_name": "name", "note": "the district's display name"},
    ]

    table_notes, column_notes = await fetch_note_overrides(_FakeHttpClient(payload=payload))  # type: ignore[arg-type]

    assert table_notes == {"districts": "an admin's own table note"}
    assert column_notes == {"districts": {"name": "the district's display name"}}


async def test_fetch_note_overrides_degrades_quietly_when_web_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schema_card.settings, "web_base_url", "http://web.local")

    table_notes, column_notes = await fetch_note_overrides(_FakeHttpClient(raise_error=True))  # type: ignore[arg-type]

    assert table_notes == {}
    assert column_notes == {}


async def test_list_schema_tables_merges_column_notes_onto_the_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schema_card.settings, "web_base_url", "http://web.local")
    payload = [
        {"table_name": "districts", "column_name": "name", "note": "the district's display name"}
    ]

    tables = await list_schema_tables(_FakePool(), _FakeHttpClient(payload=payload))  # type: ignore[arg-type]

    districts = next(t for t in tables if t.name == "districts")
    name_col = next(c for c in districts.columns if c.name == "name")
    assert name_col.note == "the district's display name"
    assert (
        districts.note == "75 UP districts, each under one division, each division under one zone."
    )


async def test_sample_table_rejects_an_unknown_table_name() -> None:
    with pytest.raises(ValueError):
        await sample_table(_FakePool(table_exists=False), "not_a_real_table")  # type: ignore[arg-type]


async def test_sample_table_returns_stringified_rows() -> None:
    rows = await sample_table(_FakePool(), "districts")  # type: ignore[arg-type]
    assert rows == [{"id": "1", "amount_inr": None}]
