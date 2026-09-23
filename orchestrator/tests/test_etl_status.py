"""etl_status.py's list_ingestion_runs()/list_quarantine() against the real
local Postgres — behind GET /etl/runs and GET /etl/quarantine (ROADMAP.md
Milestone 5's admin ETL visibility screen).

Needs excise_ro granted USAGE + SELECT on schema etl (db/roles.sql,
OPERATOR_SETUP.md §Data bank).
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

import app.sql.runner as runner
from app.etl_status import list_ingestion_runs, list_quarantine

_ETL_ENV = Path(__file__).resolve().parents[2] / "etl" / ".env"
_TEST_SOURCE = "test-etl-status-fixture"


def _etl_dsn() -> str:
    match = re.search(r"^DATABASE_URL_ETL=(.+)$", _ETL_ENV.read_text(), re.MULTILINE)
    assert match, "etl/.env missing DATABASE_URL_ETL — needed to seed etl.* fixtures for this test"
    return match.group(1).strip()


@pytest.fixture(autouse=True)
async def _reset_pool() -> AsyncIterator[None]:
    """etl_status.py reuses sql/runner.py's module-level pool, bound to the
    event loop it was first created on — pytest-asyncio gives each test a
    fresh loop, so the pool is closed (and lazily recreated) between tests.
    """
    yield
    await runner.close_pool()


@pytest.fixture
async def seeded_runs() -> AsyncIterator[list[int]]:
    conn = await asyncpg.connect(_etl_dsn())
    ids: list[int] = []
    try:
        for i in range(3):
            run_id = await conn.fetchval(
                "INSERT INTO etl.ingestion_runs "
                "(source, source_ref, status, rows_seen, rows_upserted, rows_quarantined, "
                "started_at, finished_at) "
                "VALUES ($1, $2, 'ok', 10, 9, 1, now() - ($3 || ' minutes')::interval, now()) "
                "RETURNING id",
                _TEST_SOURCE,
                f"fixture-{i}",
                str(i),
            )
            ids.append(run_id)
        await conn.execute(
            "INSERT INTO etl.quarantine (run_id, raw_row, reason) "
            "VALUES ($1, '{\"district\": \"???\"}', 'unresolvable district alias')",
            ids[0],
        )
        yield ids
    finally:
        # etl.quarantine.run_id has no ON DELETE CASCADE — a real ingestion run's audit
        # trail should not vanish just because the run row is deleted — so the fixture's
        # own quarantine row must go first or this violates the FK.
        await conn.execute("DELETE FROM etl.quarantine WHERE run_id = ANY($1::bigint[])", ids)
        await conn.execute("DELETE FROM etl.ingestion_runs WHERE id = ANY($1::bigint[])", ids)
        await conn.close()


async def test_list_ingestion_runs_orders_newest_first(seeded_runs: list[int]) -> None:
    runs, total = await list_ingestion_runs(page=1, per_page=20)

    fixture_refs = [r.source_ref for r in runs if r.id in seeded_runs]
    assert fixture_refs == ["fixture-0", "fixture-1", "fixture-2"]
    assert total >= len(seeded_runs)


async def test_list_quarantine_scoped_to_a_run(seeded_runs: list[int]) -> None:
    rows, total = await list_quarantine(page=1, per_page=20, run_id=seeded_runs[0])

    assert total == 1
    assert rows[0].run_id == seeded_runs[0]
    assert rows[0].raw_row == {"district": "???"}
    assert rows[0].reason == "unresolvable district alias"


async def test_list_quarantine_unscoped_includes_other_runs(seeded_runs: list[int]) -> None:
    rows, _ = await list_quarantine(page=1, per_page=20)

    assert any(r.run_id == seeded_runs[0] for r in rows)
