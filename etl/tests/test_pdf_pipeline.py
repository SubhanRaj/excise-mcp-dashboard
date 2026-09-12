"""sources/pdf_pipeline.py — document_url() route-building (pure) and
sync_documents() against the real local Postgres via excise_etl.
ROADMAP.md Milestone 3 tests: correct kb.documents + kb.chunks with metadata
and source URL; re-run changes no counts; a removed upstream doc is withdrawn.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

from etl.config import settings
from etl.sources.pdf_pipeline import SourceDocRow, document_url, sync_documents

BASE_URL = "https://docsrepo.exciseup.in"
TEST_ORIGIN_REFS = ["999001", "999002"]


def _row(doc_id: int = 999001, **overrides: object) -> SourceDocRow:
    base: SourceDocRow = {
        "id": doc_id,
        "slug": "test-policy",
        "title": "Test Policy",
        "document_type": "policy",
        "language": "english",
        "markdown_path": "test-policy.md",
        "dept_slug": "excise",
        "dept_level": "department_level",
        "section_slug": "test-section",
        "division_slug": None,
        "folder_slug": None,
        "rule_set_slug": None,
        "rule_set_kind": None,
        "rule_set_name": None,
    }
    base.update(overrides)  # type: ignore[typeddict-item]  # test helper, keys always valid SourceDocRow keys
    return base


# --- document_url() — pure, no DB needed ------------------------------------


def test_document_url_rule_set() -> None:
    row = _row(rule_set_slug="excise-act-2023", rule_set_kind="rules", section_slug=None)
    assert (
        document_url(BASE_URL, row)
        == f"{BASE_URL}/documents/dept/excise/rules/excise-act-2023/test-policy"
    )


def test_document_url_policy_kind() -> None:
    row = _row(rule_set_slug="2016-policy", rule_set_kind="policy", section_slug=None)
    assert (
        document_url(BASE_URL, row)
        == f"{BASE_URL}/documents/dept/excise/policy/2016-policy/test-policy"
    )


def test_document_url_secretariat_level_alias() -> None:
    row = _row(dept_level="secretariat_level")
    assert (
        document_url(BASE_URL, row) == f"{BASE_URL}/documents/sectt/excise/test-section/test-policy"
    )


def test_document_url_division_and_folder() -> None:
    row = _row(division_slug="div", folder_slug="fold")
    assert document_url(BASE_URL, row) == (
        f"{BASE_URL}/documents/dept/excise/test-section/divisions/div/folders/fold/test-policy"
    )


def test_document_url_division_only() -> None:
    row = _row(division_slug="div")
    assert (
        document_url(BASE_URL, row)
        == f"{BASE_URL}/documents/dept/excise/test-section/divisions/div/test-policy"
    )


def test_document_url_section_only() -> None:
    row = _row()
    assert (
        document_url(BASE_URL, row) == f"{BASE_URL}/documents/dept/excise/test-section/test-policy"
    )


def test_document_url_none_without_any_context() -> None:
    assert document_url(BASE_URL, _row(section_slug=None)) is None


# --- sync_documents() — live Postgres via excise_etl ------------------------


@pytest.fixture
async def pg_conn() -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(settings.database_url_etl)
    try:
        yield conn
    finally:
        await conn.execute(
            "DELETE FROM kb.documents "
            "WHERE origin = 'pdf_pipeline' AND origin_ref = ANY($1::text[])",
            TEST_ORIGIN_REFS,
        )
        await conn.close()


async def _new_run(conn: asyncpg.Connection) -> int:
    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref) VALUES ('pdf_pipeline', 'test') "
        "RETURNING id"
    )
    assert run_id is not None
    return int(run_id)


async def test_sync_creates_document_and_chunks(
    pg_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    (tmp_path / "test-policy.md").write_text("# Test Policy\n\n## Section 1\n\nBody text.\n")
    run_id = await _new_run(pg_conn)

    counts = await sync_documents(
        pg_conn, run_id, [_row()], markdown_root=tmp_path, base_url=BASE_URL
    )

    assert (counts.seen, counts.upserted, counts.quarantined) == (1, 1, 0)
    doc = await pg_conn.fetchrow(
        "SELECT title, source_url, doc_type FROM kb.documents "
        "WHERE origin = 'pdf_pipeline' AND origin_ref = '999001'"
    )
    assert doc is not None
    assert doc["title"] == "Test Policy"
    assert doc["source_url"] == f"{BASE_URL}/documents/dept/excise/test-section/test-policy"
    chunks = await pg_conn.fetch(
        "SELECT heading_path FROM kb.chunks c JOIN kb.documents d ON d.id = c.document_id "
        "WHERE d.origin_ref = '999001' ORDER BY ord"
    )
    assert [c["heading_path"] for c in chunks] == ["Test Policy", "Test Policy > Section 1"]


async def test_rerun_unchanged_content_upserts_nothing(
    pg_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    (tmp_path / "test-policy.md").write_text("# Test Policy\n\nBody.\n")
    run_id = await _new_run(pg_conn)
    first = await sync_documents(
        pg_conn, run_id, [_row()], markdown_root=tmp_path, base_url=BASE_URL
    )
    assert first.upserted == 1

    run_id_2 = await _new_run(pg_conn)
    second = await sync_documents(
        pg_conn, run_id_2, [_row()], markdown_root=tmp_path, base_url=BASE_URL
    )
    assert (second.seen, second.upserted) == (1, 0)


async def test_document_missing_from_next_fetch_is_withdrawn(
    pg_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    (tmp_path / "test-policy.md").write_text("# Test Policy\n\nBody.\n")
    run_id = await _new_run(pg_conn)
    await sync_documents(pg_conn, run_id, [_row()], markdown_root=tmp_path, base_url=BASE_URL)

    run_id_2 = await _new_run(pg_conn)
    second = await sync_documents(pg_conn, run_id_2, [], markdown_root=tmp_path, base_url=BASE_URL)

    assert second.withdrawn == 1
    withdrawn_at = await pg_conn.fetchval(
        "SELECT withdrawn_at FROM kb.documents WHERE origin_ref = '999001'"
    )
    assert withdrawn_at is not None


async def test_missing_markdown_file_is_quarantined(
    pg_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    run_id = await _new_run(pg_conn)
    row = _row(markdown_path="does-not-exist.md")
    counts = await sync_documents(pg_conn, run_id, [row], markdown_root=tmp_path, base_url=BASE_URL)
    assert (counts.quarantined, counts.upserted) == (1, 0)


async def test_no_url_context_is_quarantined(pg_conn: asyncpg.Connection, tmp_path: Path) -> None:
    (tmp_path / "test-policy.md").write_text("# X\n")
    run_id = await _new_run(pg_conn)
    row = _row(section_slug=None)
    counts = await sync_documents(pg_conn, run_id, [row], markdown_root=tmp_path, base_url=BASE_URL)
    assert counts.quarantined == 1
