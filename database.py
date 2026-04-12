from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import asyncpg

_pool: asyncpg.Pool | None = None


async def init_db() -> None:
    global _pool
    _pool = await asyncpg.create_pool(dsn=os.environ["DATABASE_URL"], min_size=1, max_size=5)

    await _pool.execute(
        """
        CREATE TABLE IF NOT EXISTS triage_results (
            id          SERIAL PRIMARY KEY,
            ticket_id   TEXT NOT NULL,
            triaged_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            ticket      JSONB NOT NULL,
            result      JSONB NOT NULL
        )
        """
    )


async def close_db() -> None:
    if _pool:
        await _pool.close()


async def save_triage_result(ticket_data: dict, result_data: dict) -> None:
    await _pool.execute(
        "INSERT INTO triage_results (ticket_id, ticket, result) VALUES ($1, $2, $3)",
        ticket_data["id"],
        json.dumps(ticket_data),
        json.dumps(result_data),
    )


async def get_all_results() -> list[dict]:
    rows = await _pool.fetch(
        "SELECT id, ticket_id, triaged_at, ticket, result FROM triage_results ORDER BY triaged_at DESC"
    )
    return [
        {
            "id": row["id"],
            "ticket_id": row["ticket_id"],
            "triaged_at": row["triaged_at"].isoformat(),
            "ticket": json.loads(row["ticket"]),
            "result": json.loads(row["result"]),
        }
        for row in rows
    ]
