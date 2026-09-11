"""Writes a rejected row to etl.quarantine, counted rather than inserted.
DATA_PIPELINE.md §Shared shape.
"""

import json
from collections.abc import Mapping

import asyncpg


async def record(
    conn: asyncpg.Connection, run_id: int, raw_row: Mapping[str, object], reason: str
) -> None:
    await conn.execute(
        "INSERT INTO etl.quarantine (run_id, raw_row, reason) VALUES ($1, $2, $3)",
        run_id,
        json.dumps(raw_row, default=str),
        reason,
    )
