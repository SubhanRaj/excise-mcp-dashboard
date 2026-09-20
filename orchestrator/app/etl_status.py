"""Read-only listing of etl.ingestion_runs / etl.quarantine, behind the admin
ETL visibility screen (ROADMAP.md Milestone 5). Needs excise_ro granted
USAGE + SELECT on schema etl (db/roles.sql) — OPERATOR_SETUP.md §Data bank
has the pending grant.
"""

import json

from app.schemas import IngestionRun, QuarantineRow
from app.sql.runner import get_pool

_RUNS_PAGE_QUERY = """
    SELECT id, source, source_ref, report_period, started_at, finished_at,
           status, rows_seen, rows_upserted, rows_quarantined, error
    FROM etl.ingestion_runs
    ORDER BY started_at DESC
    LIMIT $1 OFFSET $2
"""

_QUARANTINE_PAGE_QUERY = """
    SELECT id, run_id, raw_row, reason, created_at
    FROM etl.quarantine
    ORDER BY created_at DESC
    LIMIT $1 OFFSET $2
"""

_QUARANTINE_BY_RUN_QUERY = """
    SELECT id, run_id, raw_row, reason, created_at
    FROM etl.quarantine
    WHERE run_id = $1
    ORDER BY created_at DESC
    LIMIT $2 OFFSET $3
"""


async def list_ingestion_runs(page: int, per_page: int) -> tuple[list[IngestionRun], int]:
    pool = await get_pool()
    offset = (page - 1) * per_page
    rows = await pool.fetch(_RUNS_PAGE_QUERY, per_page, offset)
    total = int(await pool.fetchval("SELECT count(*) FROM etl.ingestion_runs") or 0)
    return [IngestionRun(**dict(r)) for r in rows], total


async def list_quarantine(
    page: int, per_page: int, run_id: int | None = None
) -> tuple[list[QuarantineRow], int]:
    pool = await get_pool()
    offset = (page - 1) * per_page
    # raw_row is jsonb; asyncpg hands it back as a JSON string with no codec
    # registered on this pool, so it's decoded here rather than adding one.
    if run_id is not None:
        rows = await pool.fetch(_QUARANTINE_BY_RUN_QUERY, run_id, per_page, offset)
        total = int(
            await pool.fetchval("SELECT count(*) FROM etl.quarantine WHERE run_id = $1", run_id)
            or 0
        )
    else:
        rows = await pool.fetch(_QUARANTINE_PAGE_QUERY, per_page, offset)
        total = int(await pool.fetchval("SELECT count(*) FROM etl.quarantine") or 0)
    return [
        QuarantineRow(
            id=r["id"],
            run_id=r["run_id"],
            raw_row=json.loads(r["raw_row"]),
            reason=r["reason"],
            created_at=r["created_at"],
        )
        for r in rows
    ], total
