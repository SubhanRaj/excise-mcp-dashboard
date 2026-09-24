"""`etl sync` — fetch -> normalize -> validate -> upsert -> record run.
DATA_PIPELINE.md §ETL pipeline design.
"""

import argparse
import asyncio
from collections.abc import Awaitable, Callable, Iterator
from datetime import date, datetime

import asyncpg
import structlog

from etl import db, loader, quarantine
from etl.sources import csv as csv_source
from etl.sources import excel as excel_source
from etl.sources import (
    iescms_dispatch,
    niti_brands,
    niti_facts,
    niti_policy,
    niti_shops,
    pdf_pipeline,
    sro_shops,
)
from etl.sources.base import RawRow

log = structlog.get_logger()

RowNormalizer = Callable[[asyncpg.Connection, dict[str, str]], Awaitable[dict[str, object]]]

# target_table -> normalizer turning one RawRow's raw string fields into the
# loader-ready dict. Empty until the real NITI column layout is confirmed
# (DATA_PIPELINE.md §Source adapters) — a row for an unregistered table is
# quarantined, not dropped silently.
TABLE_NORMALIZERS: dict[str, RowNormalizer] = {}


def _dispatch_source(registry_row: asyncpg.Record) -> Iterator[RawRow]:
    source = registry_row["source"]
    source_ref = registry_row["source_ref"]
    target_table = registry_row["target_table"]
    if source == "csv":
        return csv_source.read_rows(source_ref, target_table)
    if source == "excel":
        # excel source_ref is "<workbook path>#<sheet name>" — no sheet-name
        # column exists on source_registry, so the sheet rides in source_ref.
        path, _, sheet_name = source_ref.rpartition("#")
        return excel_source.read_rows(path, sheet_name, target_table)
    raise ValueError(f"unsupported source kind for etl core: {source!r}")


async def sync_one(pool: asyncpg.Pool, registry_row: asyncpg.Record, period: date | None) -> None:
    name = registry_row["name"]
    async with pool.acquire() as conn:
        if not await db.try_advisory_lock(conn, name):
            log.info("etl.sync.skipped_locked", source=name)
            return
        try:
            await _run_source(conn, registry_row, period)
        finally:
            await db.advisory_unlock(conn, name)


async def _finish_run(
    conn: asyncpg.Connection,
    registry_row: asyncpg.Record,
    run_id: int,
    *,
    seen: int,
    upserted: int,
    quarantined: int,
    error: str | None,
    status: str,
) -> None:
    await conn.execute(
        "UPDATE etl.ingestion_runs SET finished_at = now(), status = $1, rows_seen = $2, "
        "rows_upserted = $3, rows_quarantined = $4, error = $5 WHERE id = $6",
        status,
        seen,
        upserted,
        quarantined,
        error,
        run_id,
    )
    await conn.execute(
        "UPDATE etl.source_registry SET last_run_id = $1 WHERE id = $2", run_id, registry_row["id"]
    )
    log.info(
        "etl.sync.done",
        source=registry_row["name"],
        status=status,
        seen=seen,
        upserted=upserted,
        quarantined=quarantined,
    )


async def _run_source(
    conn: asyncpg.Connection, registry_row: asyncpg.Record, period: date | None
) -> None:
    name = registry_row["name"]

    # A source registered with requires_period reports a whole-file period with no
    # per-row business date (DATA_PIPELINE.md §Periodic sources without a per-row
    # date) — refuse before any I/O runs, the same way an unrecognised source kind
    # already is above, rather than silently falling back to run time.
    if registry_row["requires_period"] and period is None:
        run_id = await conn.fetchval(
            "INSERT INTO etl.ingestion_runs (source, source_ref) VALUES ($1, $2) RETURNING id",
            registry_row["source"],
            registry_row["source_ref"],
        )
        missing_period_error = (
            f"source {name!r} requires --period (e.g. --period 2026-08) but none was given"
        )
        log.error("etl.sync.failed", source=name, error=missing_period_error)
        await _finish_run(
            conn,
            registry_row,
            run_id,
            seen=0,
            upserted=0,
            quarantined=0,
            error=missing_period_error,
            status="failed",
        )
        return

    run_id = await conn.fetchval(
        "INSERT INTO etl.ingestion_runs (source, source_ref, report_period) VALUES ($1, $2, $3) "
        "RETURNING id",
        registry_row["source"],
        registry_row["source_ref"],
        period,
    )

    # niti_facts/niti_brands/niti_policy take "<path>#<kind>" in source_ref, the
    # same way iescms_dispatch's fl/cl variant does; niti_shops has one sheet
    # layout so its source_ref is a bare path.
    _special_sources = (
        "pdf_pipeline",
        "iescms_dispatch",
        "niti_shops",
        "niti_facts",
        "niti_brands",
        "niti_policy",
        "sro_shops",
    )
    if registry_row["source"] in _special_sources:
        error: str | None = None
        try:
            if registry_row["source"] == "pdf_pipeline":
                pdf_counts = await pdf_pipeline.sync(conn, run_id)
                seen, upserted, quarantined = (
                    pdf_counts.seen,
                    pdf_counts.upserted,
                    pdf_counts.quarantined,
                )
            elif registry_row["source"] == "iescms_dispatch":
                # source_ref is "<workbook path>#fl" or "#cl" — the report layout
                # rides in source_ref the same way the plain excel source's sheet name does.
                path, _, report_kind = registry_row["source_ref"].rpartition("#")
                iescms_counts = await iescms_dispatch.sync(conn, run_id, path, report_kind)
                seen, upserted, quarantined = (
                    iescms_counts.seen,
                    iescms_counts.upserted,
                    iescms_counts.quarantined,
                )
            elif registry_row["source"] == "niti_shops":
                shop_counts = await niti_shops.sync(conn, run_id, registry_row["source_ref"])
                seen, upserted, quarantined = (
                    shop_counts.seen,
                    shop_counts.upserted,
                    shop_counts.quarantined,
                )
            elif registry_row["source"] == "niti_facts":
                path, _, kind = registry_row["source_ref"].rpartition("#")
                fact_counts = await niti_facts.sync(conn, run_id, path, kind)
                seen, upserted, quarantined = (
                    fact_counts.seen,
                    fact_counts.upserted,
                    fact_counts.quarantined,
                )
            elif registry_row["source"] == "niti_brands":
                path, _, kind = registry_row["source_ref"].rpartition("#")
                brand_counts = await niti_brands.sync(conn, run_id, path, kind)
                seen, upserted, quarantined = (
                    brand_counts.seen,
                    brand_counts.upserted,
                    brand_counts.quarantined,
                )
            elif registry_row["source"] == "sro_shops":
                # source_ref is "<D1 backup .sql path>#FYyyyy-yy" — the snapshot's own
                # financial year, same "<path>#kind" shape niti_facts/brands/policy use.
                path, _, fy_label = registry_row["source_ref"].rpartition("#")
                sro_counts = await sro_shops.sync(conn, run_id, path, fy_label)
                seen, upserted, quarantined = (
                    sro_counts.seen,
                    sro_counts.upserted,
                    sro_counts.quarantined,
                )
            else:
                path, _, kind = registry_row["source_ref"].rpartition("#")
                policy_counts = await niti_policy.sync(conn, run_id, path, kind)
                seen, upserted, quarantined = (
                    policy_counts.seen,
                    policy_counts.upserted,
                    policy_counts.quarantined,
                )
        except Exception as exc:  # noqa: BLE001 — surfaced via the typed run row, not a crash
            seen = upserted = quarantined = 0
            error = str(exc)
            log.error("etl.sync.failed", source=name, error=error)
        status = "failed" if error else ("partial" if quarantined else "ok")
        await _finish_run(
            conn,
            registry_row,
            run_id,
            seen=seen,
            upserted=upserted,
            quarantined=quarantined,
            error=error,
            status=status,
        )
        return

    seen = upserted = quarantined = 0
    error = None
    status = "ok"
    try:
        for raw in _dispatch_source(registry_row):
            seen += 1
            normalizer = TABLE_NORMALIZERS.get(raw.target_table)
            if normalizer is None:
                await quarantine.record(
                    conn,
                    run_id,
                    raw.fields,
                    f"no normalizer registered for table: {raw.target_table}",
                )
                quarantined += 1
                continue
            try:
                normalized = await normalizer(conn, raw.fields)
                normalized["source_ref"] = raw.source_ref
                await loader.upsert(conn, raw.target_table, normalized)
                upserted += 1
            except Exception as exc:  # noqa: BLE001 — a bad row is data, quarantine it, don't crash the run
                await quarantine.record(conn, run_id, raw.fields, str(exc))
                quarantined += 1
        if quarantined:
            status = "partial"
    except Exception as exc:
        error = str(exc)
        status = "failed"
        log.error("etl.sync.failed", source=name, error=error)

    await _finish_run(
        conn,
        registry_row,
        run_id,
        seen=seen,
        upserted=upserted,
        quarantined=quarantined,
        error=error,
        status=status,
    )


async def sync(source: str | None, all_sources: bool, period: date | None = None) -> None:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        if source:
            rows = await conn.fetch(
                "SELECT * FROM etl.source_registry WHERE name = $1 AND enabled", source
            )
        elif all_sources:
            rows = await conn.fetch("SELECT * FROM etl.source_registry WHERE enabled")
        else:
            raise ValueError("pass --source NAME or --all")
    for row in rows:
        await sync_one(pool, row, period)
    await db.close_pool()


def _parse_period(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="etl")
    sub = parser.add_subparsers(dest="command", required=True)
    sync_parser = sub.add_parser("sync")
    sync_parser.add_argument("--source")
    sync_parser.add_argument("--all", action="store_true")
    sync_parser.add_argument(
        "--period", help="reporting month for a requires_period source, as YYYY-MM (e.g. 2026-08)"
    )
    args = parser.parse_args()
    if args.command == "sync":
        asyncio.run(sync(args.source, args.all, _parse_period(args.period)))
