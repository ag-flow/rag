from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.sync.scheduler import schedule_due_sources
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
DEFAULT_INTERVAL = 300


async def _make_workspace(pool: asyncpg.Pool, name: str) -> str:
    async with pool.acquire() as conn:
        return await seed_workspace(conn, name=name, rag_cnx="c", rag_base="b")


async def _make_source(
    pool: asyncpg.Pool,
    ws_id: str,
    next_sync_offset_sec: int | None,
    config_extra: dict | None = None,
) -> str:
    cfg = {"url": "https://github.com/x/y", "branch": "main"}
    if config_extra:
        cfg.update(config_extra)
    async with pool.acquire() as conn:
        if next_sync_offset_sec is None:
            return await conn.fetchval(
                "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
                "VALUES ($1, 'git', $2::jsonb, NULL) RETURNING id",
                ws_id,
                json.dumps(cfg),
            )
        return await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, now() + ($3 || ' seconds')::interval) "
            "RETURNING id",
            ws_id,
            json.dumps(cfg),
            str(next_sync_offset_sec),
        )


@pytest.mark.asyncio
async def test_scheduler_creates_job_for_due_source(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_a")
    src_id = await _make_source(session_pool, ws_id, next_sync_offset_sec=-60)

    n = await schedule_due_sources(
        session_pool,
        default_interval_seconds=DEFAULT_INTERVAL,
    )
    assert n == 1

    row = await session_pool.fetchrow(
        "SELECT triggered_by, status, source_id FROM index_jobs WHERE workspace_id=$1",
        ws_id,
    )
    assert row is not None
    assert row["triggered_by"] == "schedule"
    assert row["status"] == "pending"
    assert str(row["source_id"]) == str(src_id)

    # next_sync_at bumped
    next_at = await session_pool.fetchval(
        "SELECT next_sync_at FROM workspace_sources WHERE id=$1", src_id
    )
    assert next_at is not None


@pytest.mark.asyncio
async def test_scheduler_skips_source_with_pending_job(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_b")
    src_id = await _make_source(session_pool, ws_id, next_sync_offset_sec=-60)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending')",
            ws_id,
            src_id,
        )

    n = await schedule_due_sources(
        session_pool,
        default_interval_seconds=DEFAULT_INTERVAL,
    )
    assert n == 0


@pytest.mark.asyncio
async def test_scheduler_skips_future_sources(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_c")
    await _make_source(session_pool, ws_id, next_sync_offset_sec=3600)  # +1h

    n = await schedule_due_sources(
        session_pool,
        default_interval_seconds=DEFAULT_INTERVAL,
    )
    assert n == 0


@pytest.mark.asyncio
async def test_scheduler_uses_per_source_interval_override(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id = await _make_workspace(session_pool, "ws_sched_d")
    src_id = await _make_source(
        session_pool,
        ws_id,
        next_sync_offset_sec=-60,
        config_extra={"sync_interval_seconds": 60},
    )

    await schedule_due_sources(
        session_pool,
        default_interval_seconds=DEFAULT_INTERVAL,
    )
    # next_sync_at doit être ~now()+60s, pas now()+300s
    next_at = await session_pool.fetchval(
        "SELECT EXTRACT(EPOCH FROM (next_sync_at - now())) FROM workspace_sources WHERE id=$1",
        src_id,
    )
    assert 50 <= float(next_at) <= 70
