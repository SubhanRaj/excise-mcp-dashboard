"""asyncpg pool on the excise_ro role: READ ONLY txn, statement timeout, row cap.
MCP_ENGINES.md §run_sql.
"""

import asyncpg

from app.config import settings
from app.schemas import QueryTimeoutError, SqlExecutionError

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url_readonly, min_size=1, max_size=5)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def run_sql(sql: str, row_limit: int) -> list[dict[str, object]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            await conn.execute(f"SET LOCAL statement_timeout = '{settings.statement_timeout}'")
            await conn.execute("SET LOCAL idle_in_transaction_session_timeout = '15s'")
            try:
                rows = await conn.fetch(sql)
            except asyncpg.QueryCanceledError as e:
                raise QueryTimeoutError() from e
            except asyncpg.PostgresError as e:
                raise SqlExecutionError(str(e)) from e
    return [dict(r) for r in rows[:row_limit]]
