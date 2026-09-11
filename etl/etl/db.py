"""Writer pool on the excise_etl role. db/roles.sql grants it INSERT/UPDATE/DELETE on
public.* + kb.* + etl.*, no DDL — this module never issues CREATE/ALTER.
"""

import asyncpg

from etl.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url_etl, min_size=1, max_size=4)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def try_advisory_lock(conn: asyncpg.Connection, source_name: str) -> bool:
    """Postgres session-level advisory lock keyed by source name, so overlapping
    timers for the same source cannot double-load. DATA_PIPELINE.md §Schedules.
    """
    return bool(await conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", source_name))


async def advisory_unlock(conn: asyncpg.Connection, source_name: str) -> None:
    await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", source_name)
