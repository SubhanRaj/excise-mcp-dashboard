"""kb/retrieve.py against the real local Postgres. ROADMAP.md Milestone 3
tests: retrieval returns the expected chunk by FTS rank; a withdrawn document
is excluded; an empty corpus / no match returns no context.

Fixture rows are seeded via excise_etl (the write role) and read back through
excise_ro (retrieve.py's own pool) — the same split as real ingest/retrieve.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

import app.sql.runner as runner
from app.kb.retrieve import retrieve

_ETL_ENV = Path(__file__).resolve().parents[2] / "etl" / ".env"
_TEST_ORIGIN_REF = "retrieve-fixture"


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
async def seeded_document() -> AsyncIterator[int]:
    conn = await asyncpg.connect(_etl_dsn())
    try:
        doc_id = await conn.fetchval(
            "INSERT INTO kb.documents (origin, origin_ref, title, doc_type, content_sha256) "
            "VALUES ('test', $1, 'MGQ Test Policy', 'policy', 'deadbeef') RETURNING id",
            _TEST_ORIGIN_REF,
        )
        # denser term match -> higher ts_rank, should come back first
        await conn.execute(
            "INSERT INTO kb.chunks (document_id, ord, heading_path, content, token_estimate) "
            "VALUES ($1, 0, 'Section 12', "
            "'The minimum guaranteed quota is fixed annually. "
            "Minimum guaranteed quota applies to every licensed shop.', 25)",
            doc_id,
        )
        await conn.execute(
            "INSERT INTO kb.chunks (document_id, ord, heading_path, content, token_estimate) "
            "VALUES ($1, 1, 'Section 20', "
            "'Guaranteed minimum quota may be reviewed once by policy note.', 15)",
            doc_id,
        )
        yield doc_id
    finally:
        await conn.execute("DELETE FROM kb.documents WHERE id = $1", doc_id)
        await conn.close()


async def test_retrieve_ranks_denser_match_first(seeded_document: int) -> None:
    chunks = await retrieve("minimum guaranteed quota", k=6)
    assert len(chunks) == 2
    assert chunks[0].heading_path == "Section 12"
    assert chunks[0].title == "MGQ Test Policy"
    assert chunks[0].rank >= chunks[1].rank


async def test_retrieve_excludes_withdrawn_documents(seeded_document: int) -> None:
    conn = await asyncpg.connect(_etl_dsn())
    try:
        await conn.execute(
            "UPDATE kb.documents SET withdrawn_at = now() WHERE id = $1", seeded_document
        )
    finally:
        await conn.close()

    chunks = await retrieve("minimum guaranteed quota", k=6)
    assert chunks == []


async def test_retrieve_no_match_returns_empty() -> None:
    chunks = await retrieve("xyzzy nonexistent gibberish query term", k=6)
    assert chunks == []
