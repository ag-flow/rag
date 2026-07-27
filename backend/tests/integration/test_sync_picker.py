from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.sync.executor import pick_next_pending_job
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _setup_ws_src_indexer(
    pool: asyncpg.Pool, name: str, *, owner_id: str | None = None
) -> tuple[str, str]:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=name, rag_cnx="c", rag_base="b", owner_id=owner_id)
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


async def _insert_job(pool: asyncpg.Pool, ws_id: str, src_id: str, status: str) -> str:
    return await pool.fetchval(
        "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
        "VALUES ($1, $2, 'manual', $3) RETURNING id",
        ws_id,
        src_id,
        status,
    )


async def _finish_jobs(pool: asyncpg.Pool, *job_ids: str) -> None:
    await pool.execute(
        "UPDATE index_jobs SET status='done', finished_at=now() WHERE id = ANY($1::uuid[])",
        list(job_ids),
    )


@pytest.mark.asyncio
async def test_picker_excludes_workspace_with_running_job(
    session_pool: asyncpg.Pool,
) -> None:
    """Un seul job running par workspace : le pending du même workspace attend."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_id, src_id = await _setup_ws_src_indexer(session_pool, "ws_pick_excl", owner_id="own_excl")
    running = await _insert_job(session_pool, ws_id, src_id, "running")
    pending = await _insert_job(session_pool, ws_id, src_id, "pending")

    result = await pick_next_pending_job(session_pool)
    assert result is None

    await _finish_jobs(session_pool, running)
    result = await pick_next_pending_job(session_pool)
    assert result is not None
    assert str(result.job_id) == str(pending)
    await _finish_jobs(session_pool, pending)


@pytest.mark.asyncio
async def test_picker_prefers_owner_without_running_job(
    session_pool: asyncpg.Pool,
) -> None:
    """Équité : le job (plus récent) de l'owner B passe devant celui de
    l'owner A dont un job tourne déjà — A ne bloque pas B (feature a9719d13)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    ws_a1, src_a1 = await _setup_ws_src_indexer(session_pool, "ws_fair_a1", owner_id="own_a")
    ws_a2, src_a2 = await _setup_ws_src_indexer(session_pool, "ws_fair_a2", owner_id="own_a")
    ws_b, src_b = await _setup_ws_src_indexer(session_pool, "ws_fair_b", owner_id="own_b")

    running_a = await _insert_job(session_pool, ws_a1, src_a1, "running")
    pending_a = await _insert_job(session_pool, ws_a2, src_a2, "pending")  # plus ancien
    pending_b = await _insert_job(session_pool, ws_b, src_b, "pending")  # plus récent

    result = await pick_next_pending_job(session_pool)
    assert result is not None
    assert str(result.job_id) == str(pending_b)

    # B occupe désormais un slot lui aussi : retour au FIFO → job de A.
    result2 = await pick_next_pending_job(session_pool)
    assert result2 is not None
    assert str(result2.job_id) == str(pending_a)

    await _finish_jobs(session_pool, running_a, pending_a, pending_b)
