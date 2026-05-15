from __future__ import annotations

import asyncio
import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
from rag.sync.repo_storage import RepoStorage
from rag.sync.worker import SyncWorker
from tests.integration._git_fixture import make_bare_repo_with_commits

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    def resolve_with_retry(self, ref: str) -> str:
        return "tok-x"


@pytest.mark.asyncio
async def test_worker_processes_pending_job_within_one_cycle(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    """SyncWorker démarré → en 1 tick, le job pending passe en done."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_worker_a', 'h', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        src_id = await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, NULL) RETURNING id",
            ws_id,
            json.dumps({"url": f"file://{bare}", "branch": "main"}),
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending') RETURNING id",
            ws_id,
            src_id,
        )

    worker = SyncWorker(
        config_pool=session_pool,
        storage=RepoStorage(root=tmp_path / "repos"),
        indexer=NoOpIndexer(session_pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        poll_interval_seconds=1,
        default_sync_interval_seconds=300,
    )
    await worker.start()
    # Laisse le worker traiter 1 cycle
    await asyncio.sleep(2)
    await worker.stop()

    status = await session_pool.fetchval(
        "SELECT status FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert status == "done"


@pytest.mark.asyncio
async def test_worker_schedules_due_sources(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    """Worker → scheduler crée un job pour une source dont next_sync_at est passé."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base) "
            "VALUES ('ws_worker_b', 'h', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, now() - interval '60 seconds')",
            ws_id,
            json.dumps({"url": f"file://{bare}", "branch": "main"}),
        )

    worker = SyncWorker(
        config_pool=session_pool,
        storage=RepoStorage(root=tmp_path / "repos"),
        indexer=NoOpIndexer(session_pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        poll_interval_seconds=1,
        default_sync_interval_seconds=300,
    )
    await worker.start()
    await asyncio.sleep(3)
    await worker.stop()

    # Un job triggered_by=schedule existe et est done
    row = await session_pool.fetchrow(
        "SELECT triggered_by, status FROM index_jobs WHERE workspace_id=$1",
        ws_id,
    )
    assert row is not None
    assert row["triggered_by"] == "schedule"
    assert row["status"] == "done"


@pytest.mark.asyncio
async def test_worker_stop_idempotent(session_pool: asyncpg.Pool, tmp_path: Path) -> None:
    """Stop sans start ou stop appelé deux fois ne lève pas."""
    worker = SyncWorker(
        config_pool=session_pool,
        storage=RepoStorage(root=tmp_path / "repos"),
        indexer=NoOpIndexer(session_pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        poll_interval_seconds=30,
        default_sync_interval_seconds=300,
    )
    await worker.stop()  # avant start
    await worker.start()
    await worker.stop()
    await worker.stop()  # idempotent
