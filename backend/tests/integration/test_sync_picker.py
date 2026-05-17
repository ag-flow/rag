from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.sync.executor import pick_next_pending_job
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _setup_ws_src_indexer(pool: asyncpg.Pool, name: str) -> tuple[str, str]:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=name, rag_cnx="c", rag_base="b")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        src_id = await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, NULL) RETURNING id",
            ws_id,
            json.dumps({"url": "https://github.com/x/y", "branch": "main"}),
        )
        return ws_id, src_id


@pytest.mark.asyncio
async def test_picker_returns_none_when_no_pending(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    result = await pick_next_pending_job(session_pool)
    assert result is None


@pytest.mark.asyncio
async def test_picker_transitions_pending_to_running(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id, src_id = await _setup_ws_src_indexer(session_pool, "ws_pick_a")
    async with session_pool.acquire() as conn:
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending') RETURNING id",
            ws_id,
            src_id,
        )

    result = await pick_next_pending_job(session_pool)
    assert result is not None
    assert str(result.job_id) == str(job_id)
    assert str(result.workspace_id) == str(ws_id)
    assert result.workspace_name == "ws_pick_a"
    assert str(result.source_id) == str(src_id)
    assert result.indexer_provider == "openai"
    assert result.indexer_model == "text-embedding-3-small"
    assert result.indexer_used == "openai/text-embedding-3-small"

    # Job passé en running
    status = await session_pool.fetchval(
        "SELECT status FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert status == "running"


@pytest.mark.asyncio
async def test_picker_skips_non_pending_jobs(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id, src_id = await _setup_ws_src_indexer(session_pool, "ws_pick_b")
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status, finished_at) "
            "VALUES ($1, $2, 'manual', 'done', now())",
            ws_id,
            src_id,
        )

    result = await pick_next_pending_job(session_pool)
    assert result is None
