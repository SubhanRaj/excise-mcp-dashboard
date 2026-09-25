"""pdf-markdown-pipeline sync — the department's verified document repository
into kb.documents / kb.chunks. DATA_PIPELINE.md §pdf-markdown-pipeline sync.

Reads two read-only sources on the same box: MariaDB `pdf_markdown_pipeline_local`
(via excise_mcp_kb_ro) for document metadata, and that app's own storage disk
for the Markdown files. Writes kb.* as excise_etl. Never writes to
pdf-markdown-pipeline's own database.

`fetch_documents` (MariaDB) and `sync_documents` (hash/chunk/upsert/withdraw
against Postgres) are split so the ingest logic is testable against a plain
list of fixture rows, with no MariaDB driver involved.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict

import aiomysql
import asyncpg
import structlog

from etl import quarantine
from etl.chunk import chunk_markdown
from etl.config import settings

log = structlog.get_logger()

ORIGIN = "pdf_pipeline"

# Mirrors SitemapController::documentUrl() in pdf-markdown-pipeline — the exact
# route shape per document kind (rule_set/policy, folder, division, section).
# pdf-markdown-pipeline's excise department also holds ten other states' policies
# as comparative reference material (rule_sets.state tags which one) — this used to
# sync only Uttar Pradesh's own (plus a state-agnostic rs.state IS NULL doc, a
# generic Act/GO) and drop the rest as out of scope. They're in scope now: every
# state's own document syncs, carrying its rule_set.state straight onto
# kb.documents.state, the same column name and the same meaning as the source —
# NULL stays a state-agnostic Act/GO, everything else names the state its policy
# belongs to. What changed is retrieval, not ingestion: kb/retrieve.py defaults to
# Uttar Pradesh (plus state-agnostic docs) unless a question is explicitly
# comparative, the same scope this query alone used to enforce.
_DOCUMENTS_QUERY = """
    SELECT
        doc.id AS id, doc.slug AS slug, doc.title AS title,
        doc.document_type AS document_type, doc.language AS language,
        doc.markdown_path AS markdown_path, doc.metadata AS metadata,
        dept.slug AS dept_slug, dept.level AS dept_level,
        sec.slug AS section_slug,
        dv.slug AS division_slug,
        fold.slug AS folder_slug,
        rs.slug AS rule_set_slug, rs.kind AS rule_set_kind, rs.name AS rule_set_name,
        rs.state AS rule_set_state
    FROM documents doc
    JOIN departments dept ON dept.id = doc.department_id
    LEFT JOIN sections sec ON sec.id = doc.section_id
    LEFT JOIN divisions dv ON dv.id = doc.division_id
    LEFT JOIN folders fold ON fold.id = doc.folder_id
    LEFT JOIN rule_sets rs ON rs.id = doc.rule_set_id
    WHERE doc.visibility = 'public'
      AND doc.status = 'verified'
      AND doc.deleted_at IS NULL
      AND dept.slug = %s
"""


class SourceDocRow(TypedDict):
    id: int
    slug: str
    title: str
    document_type: str
    language: str
    markdown_path: str | None
    effective_year: int | None
    dept_slug: str
    dept_level: str
    section_slug: str | None
    division_slug: str | None
    folder_slug: str | None
    rule_set_slug: str | None
    rule_set_kind: str | None
    rule_set_name: str | None
    rule_set_state: str | None


@dataclass(frozen=True)
class RunCounts:
    seen: int
    upserted: int
    quarantined: int
    withdrawn: int


def _level_alias(dept_level: str) -> str:
    return "sectt" if dept_level == "secretariat_level" else "dept"


def _parse_effective_year(metadata_json: str | None) -> int | None:
    """pdf-markdown-pipeline stamps a rule/amendment's year in its own
    documents.metadata JSON (e.g. {"amendment_number": 1, "effective_year":
    2022, ...}) — this app's kb.documents.effective_from column exists for
    exactly this but was never populated, so every synced document read as
    undated past whatever year happened to be spelled out in its title text.
    Missing or malformed metadata is not a sync failure, just an undated doc.
    """
    if not metadata_json:
        return None
    try:
        year = json.loads(metadata_json).get("effective_year")
    except (json.JSONDecodeError, AttributeError):
        return None
    return year if isinstance(year, int) else None


def document_url(base_url: str, row: SourceDocRow) -> str | None:
    """The docsrepo.exciseup.in deep link for one document, or None when the
    row carries none of the section/division/folder/rule_set context a URL
    needs (a document not yet placed anywhere browsable).
    """
    level = _level_alias(row["dept_level"])
    dept = row["dept_slug"]
    slug = row["slug"]
    if row["rule_set_slug"]:
        return (
            f"{base_url}/documents/{level}/{dept}/{row['rule_set_kind']}/"
            f"{row['rule_set_slug']}/{slug}"
        )
    if row["folder_slug"] and row["division_slug"]:
        return (
            f"{base_url}/documents/{level}/{dept}/{row['section_slug']}/"
            f"divisions/{row['division_slug']}/folders/{row['folder_slug']}/{slug}"
        )
    if row["folder_slug"]:
        return (
            f"{base_url}/documents/{level}/{dept}/{row['section_slug']}/"
            f"folders/{row['folder_slug']}/{slug}"
        )
    if row["division_slug"]:
        return (
            f"{base_url}/documents/{level}/{dept}/{row['section_slug']}/"
            f"divisions/{row['division_slug']}/{slug}"
        )
    if row["section_slug"]:
        return f"{base_url}/documents/{level}/{dept}/{row['section_slug']}/{slug}"
    return None


async def fetch_documents(department_slug: str) -> list[SourceDocRow]:
    conn = await aiomysql.connect(
        host=settings.kb_ro_mysql_host,
        port=settings.kb_ro_mysql_port,
        user=settings.kb_ro_mysql_user,
        password=settings.kb_ro_mysql_password,
        db=settings.kb_ro_mysql_database,
    )
    try:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(_DOCUMENTS_QUERY, (department_slug,))
            raw_rows = await cur.fetchall()
    finally:
        conn.close()
    return [
        SourceDocRow(
            id=r["id"],
            slug=r["slug"],
            title=r["title"],
            document_type=r["document_type"],
            language=r["language"],
            markdown_path=r["markdown_path"],
            effective_year=_parse_effective_year(r["metadata"]),
            dept_slug=r["dept_slug"],
            dept_level=r["dept_level"],
            section_slug=r["section_slug"],
            division_slug=r["division_slug"],
            folder_slug=r["folder_slug"],
            rule_set_slug=r["rule_set_slug"],
            rule_set_kind=r["rule_set_kind"],
            rule_set_name=r["rule_set_name"],
            rule_set_state=r["rule_set_state"],
        )
        for r in raw_rows
    ]


async def sync_documents(
    pg_conn: asyncpg.Connection,
    run_id: int,
    rows: list[SourceDocRow],
    markdown_root: Path,
    base_url: str,
    # Withdrawal below is scoped by this origin alone, against whatever rows this one
    # call happens to pass — real production data and a test's own fixture rows share
    # a database, so a caller other than sync() must pass its own distinct origin here
    # or its withdrawal UPDATE reaches every real row of the default origin too.
    origin: str = ORIGIN,
) -> RunCounts:
    seen = upserted = quarantined = 0
    fetched_refs: list[str] = []

    for row in rows:
        seen += 1
        origin_ref = str(row["id"])
        fetched_refs.append(origin_ref)

        url = document_url(base_url, row)
        if url is None:
            await quarantine.record(
                pg_conn, run_id, dict(row), "no section/rule_set context to build a source URL"
            )
            quarantined += 1
            continue
        if not row["markdown_path"]:
            await quarantine.record(pg_conn, run_id, dict(row), "markdown_path is empty")
            quarantined += 1
            continue

        try:
            markdown = (markdown_root / row["markdown_path"]).read_text(encoding="utf-8")
        except OSError as exc:
            await quarantine.record(pg_conn, run_id, dict(row), f"markdown file unreadable: {exc}")
            quarantined += 1
            continue

        content_sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        effective_from = date(row["effective_year"], 1, 1) if row["effective_year"] else None
        existing = await pg_conn.fetchrow(
            "SELECT content_sha256, effective_from, state, withdrawn_at FROM kb.documents "
            "WHERE origin = $1 AND origin_ref = $2",
            origin,
            origin_ref,
        )
        if (
            existing
            and existing["content_sha256"] == content_sha256
            and existing["effective_from"] == effective_from
            and existing["state"] == row["rule_set_state"]
            and existing["withdrawn_at"] is None
        ):
            continue  # unchanged and live — re-running the same corpus changes no rows

        document_id = await pg_conn.fetchval(
            """
            INSERT INTO kb.documents
                (origin, origin_ref, title, doc_type, language, department, rule_set, state,
                 effective_from, source_url, content_sha256, ingested_at, withdrawn_at)
            VALUES ($1, $2, $3, $4, $5, 'excise', $6, $7, $8, $9, $10, now(), NULL)
            ON CONFLICT (origin, origin_ref) DO UPDATE SET
                title = EXCLUDED.title, doc_type = EXCLUDED.doc_type,
                language = EXCLUDED.language, rule_set = EXCLUDED.rule_set,
                state = EXCLUDED.state,
                effective_from = EXCLUDED.effective_from,
                source_url = EXCLUDED.source_url, content_sha256 = EXCLUDED.content_sha256,
                ingested_at = now(), withdrawn_at = NULL
            RETURNING id
            """,
            origin,
            origin_ref,
            row["title"],
            row["document_type"],
            row["language"],
            row["rule_set_name"],
            row["rule_set_state"],
            effective_from,
            url,
            content_sha256,
        )
        chunks = chunk_markdown(markdown)
        async with pg_conn.transaction():
            await pg_conn.execute("DELETE FROM kb.chunks WHERE document_id = $1", document_id)
            for ord_, chunk in enumerate(chunks):
                await pg_conn.execute(
                    "INSERT INTO kb.chunks "
                    "(document_id, ord, heading_path, content, token_estimate) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    document_id,
                    ord_,
                    chunk.heading_path,
                    chunk.content,
                    chunk.token_estimate,
                )
        upserted += 1

    withdrawn_rows = await pg_conn.fetch(
        "UPDATE kb.documents SET withdrawn_at = now() "
        "WHERE origin = $1 AND withdrawn_at IS NULL AND NOT (origin_ref = ANY($2::text[])) "
        "RETURNING id",
        origin,
        fetched_refs,
    )

    return RunCounts(
        seen=seen, upserted=upserted, quarantined=quarantined, withdrawn=len(withdrawn_rows)
    )


async def sync(pg_conn: asyncpg.Connection, run_id: int) -> RunCounts:
    rows = await fetch_documents(settings.pdf_pipeline_department_slug)
    counts = await sync_documents(
        pg_conn,
        run_id,
        rows,
        markdown_root=Path(settings.pdf_pipeline_root),
        base_url=settings.pdf_pipeline_base_url,
    )
    if counts.withdrawn:
        log.info("etl.pdf_pipeline.withdrawn", count=counts.withdrawn)
    return counts
