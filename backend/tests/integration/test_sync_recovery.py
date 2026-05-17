from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.sync.recovery import reset_stale_running_jobs
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _make_running_job(pool: asyncpg.Pool, ws_id, started_at_offset_sec: int = 0):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, started_at) "
            "VALUES ($1, 'manual', 'running', now() - ($2 || ' seconds')::interval) "
            "RETURNING id",
            ws_id,
            str(started_at_offset_sec),
        )


@pytest.mark.asyncio
async def test_reset_marks_running_as_error(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_rec_a", rag_cnx="c", rag_base="b")
    job_id = await _make_running_job(session_pool, ws_id, started_at_offset_sec=300)

    count = await reset_stale_running_jobs(session_pool)
    assert count == 1

    row = await session_pool.fetchrow(
        "SELECT status, error_message, finished_at, duration_ms FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert row is not None
    assert row["status"] == "error"
    assert row["error_message"] == "stale_at_boot"
    assert row["finished_at"] is not None
    assert row["duration_ms"] is not None
    assert row["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_reset_does_not_touch_pending_or_done(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_rec_b", rag_cnx="c", rag_base="b")
        pending_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'manual', 'pending') RETURNING id",
            ws_id,
        )
        done_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, finished_at) "
            "VALUES ($1, 'manual', 'done', now()) RETURNING id",
            ws_id,
        )

    count = await reset_stale_running_jobs(session_pool)
    assert count == 0

    pending_status = await session_pool.fetchval(
        "SELECT status FROM index_jobs WHERE id=$1", pending_id
    )
    done_status = await session_pool.fetchval("SELECT status FROM index_jobs WHERE id=$1", done_id)
    assert pending_status == "pending"
    assert done_status == "done"
