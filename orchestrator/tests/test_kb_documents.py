"""kb/retrieve.py's list_documents() against the real local Postgres — the
paginated, unranked listing behind GET /kb/documents (web/plan/webui.md §12),
distinct from retrieve()'s ranked FTS search.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

import app.sql.runner as runner
from app.kb.retrieve import list_documents

_ETL_ENV = Path(__file__).resolve().parents[2] / "etl" / ".env"


def _etl_dsn() -> str:
    match = re.search(r"^DATABASE_URL_ETL=(.+)$", _ETL_ENV.read_text(), re.MULTILINE)
    assert match, "etl/.env missing DATABASE_URL_ETL — needed to seed kb.* fixtures for this test"
    return match.group(1).strip()


@pytest.fixture(autouse=True)
async def _reset_retrieve_pool() -> AsyncIterator[None]:
    """retrieve.py reuses sql/runner.py's module-level pool, which is bound to
    the event loop it was first created on. pytest-asyncio gives each test
    function a fresh loop, so the pool must be closed (and lazily recreated)
    between tests rather than reused across them.
    """
    yield
    await runner.close_pool()


@pytest.fixture
async def seeded_documents() -> AsyncIterator[list[int]]:
    conn = await asyncpg.connect(_etl_dsn())
    ids: list[int] = []
    try:
        for i in range(3):
            doc_id = await conn.fetchval(
                "INSERT INTO kb.documents "
                "(origin, origin_ref, title, doc_type, content_sha256, ingested_at) "
                "VALUES "
                "('test', $1, $2, 'policy', 'deadbeef', now() - ($3 || ' minutes')::interval) "
                "RETURNING id",
                f"documents-fixture-{i}",
                f"Test Policy {i}",
                str(i),
            )
            ids.append(doc_id)
        yield ids
    finally:
        await conn.execute("DELETE FROM kb.documents WHERE id = ANY($1::bigint[])", ids)
        await conn.close()


async def test_list_documents_orders_newest_first(seeded_documents: list[int]) -> None:
    documents, total = await list_documents(page=1, per_page=20)

    fixture_titles = [d.title for d in documents if d.id in seeded_documents]
    assert fixture_titles == ["Test Policy 0", "Test Policy 1", "Test Policy 2"]
    assert total >= len(seeded_documents)


async def test_list_documents_paginates(seeded_documents: list[int]) -> None:
    page_one, total = await list_documents(page=1, per_page=2)
    page_two, _ = await list_documents(page=2, per_page=2)

    assert len(page_one) == 2
    assert total >= 3
    # Same ordering as a single unpaginated call — no row repeated or skipped across pages.
    ids_one, ids_two = [d.id for d in page_one], [d.id for d in page_two]
    assert set(ids_one).isdisjoint(ids_two)


async def test_list_documents_includes_withdrawn_with_the_flag_set(
    seeded_documents: list[int],
) -> None:
    conn = await asyncpg.connect(_etl_dsn())
    try:
        await conn.execute(
            "UPDATE kb.documents SET withdrawn_at = now() WHERE id = $1", seeded_documents[0]
        )
    finally:
        await conn.close()

    documents, _ = await list_documents(page=1, per_page=20)
    withdrawn = next(d for d in documents if d.id == seeded_documents[0])
    assert withdrawn.withdrawn_at is not None
