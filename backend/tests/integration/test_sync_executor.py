from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
from rag.sync.executor import execute_next_pending_job
from rag.sync.repo_storage import RepoStorage
from tests.integration._git_fixture import add_commit, make_bare_repo_with_commits
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    """Stub : retourne 'tok-x' quel que soit le ref demandé."""

    async def resolve_with_retry(self, ref: str) -> str:
        return "tok-x"


class _StubClientProvider:
    """Stub : default vault 'rag' (None pour simuler l'absence de coffre)."""

    def __init__(self, default_name: str | None = "rag") -> None:
        self._name = default_name

    async def get_default_vault_name(self) -> str | None:
        return self._name


async def _make_workspace_with_indexer(
    pool: asyncpg.Pool,
    name: str,
) -> str:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=name, rag_cnx="c", rag_base="b")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
    return ws_id


async def _make_source(
    pool: asyncpg.Pool,
    ws_id: str,
    url: str,
    branch: str = "main",
    auth_ref: str | None = None,
) -> str:
    cfg: dict[str, Any] = {"url": url, "branch": branch}
    if auth_ref:
        cfg["auth_ref"] = auth_ref
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
            "VALUES ($1, 'git', $2::jsonb, now()) RETURNING id",
            ws_id,
            json.dumps(cfg),
        )


async def _make_pending_job(pool: asyncpg.Pool, ws_id: str, src_id: str) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status) "
            "VALUES ($1, $2, 'manual', 'pending') RETURNING id",
            ws_id,
            src_id,
        )


@pytest.mark.asyncio
async def test_executor_first_sync_all_files_indexed(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(
        tmp_path,
        {"a.md": "v1", "b.md": "v1"},
    )

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_a")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    job_id = await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    processed = await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )
    assert processed is True

    row = await session_pool.fetchrow(
        "SELECT status, files_changed, files_skipped, finished_at FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert row["status"] == "done"
    assert row["files_changed"] == 2
    assert row["files_skipped"] == 0
    assert row["finished_at"] is not None

    docs = await session_pool.fetch(
        "SELECT path FROM indexed_documents WHERE workspace_id=$1 ORDER BY path",
        ws_id,
    )
    assert [r["path"] for r in docs] == ["a.md", "b.md"]


@pytest.mark.asyncio
async def test_executor_second_sync_no_change_skips_all(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1", "b.md": "v1"})

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_b")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    # 2e sync : nouveau job pending sans changement remote
    job2_id = await _make_pending_job(session_pool, ws_id, src_id)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    row = await session_pool.fetchrow(
        "SELECT status, files_changed, files_skipped FROM index_jobs WHERE id=$1",
        job2_id,
    )
    assert row["status"] == "done"
    assert row["files_changed"] == 0
    assert row["files_skipped"] == 2


@pytest.mark.asyncio
async def test_executor_second_sync_detects_modify_and_delete(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1", "b.md": "v1"})

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_c")
    src_id = await _make_source(session_pool, ws_id, url=f"file://{bare}")
    await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    # Modifie b.md, ajoute c.md, supprime a.md
    work = tmp_path / "work"
    add_commit(work, files={"b.md": "v2", "c.md": "v1"}, deletes=["a.md"])

    job2_id = await _make_pending_job(session_pool, ws_id, src_id)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    row = await session_pool.fetchrow(
        "SELECT files_changed, files_skipped FROM index_jobs WHERE id=$1",
        job2_id,
    )
    # b modifié (1) + c ajouté (1) + a supprimé (1) = 3 changes
    assert row["files_changed"] == 3
    assert row["files_skipped"] == 0

    docs = await session_pool.fetch(
        "SELECT path FROM indexed_documents WHERE workspace_id=$1 ORDER BY path",
        ws_id,
    )
    paths = [r["path"] for r in docs]
    assert "a.md" not in paths  # deleted
    assert "b.md" in paths
    assert "c.md" in paths


@pytest.mark.asyncio
async def test_executor_failure_on_invalid_url_marks_error(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    ws_id = await _make_workspace_with_indexer(session_pool, "ws_exec_d")
    src_id = await _make_source(
        session_pool,
        ws_id,
        url="file:///nonexistent/repo.git",
    )
    job_id = await _make_pending_job(session_pool, ws_id, src_id)

    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )

    row = await session_pool.fetchrow(
        "SELECT status, error_message FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert row["status"] == "error"
    assert "git clone failed" in row["error_message"]


@pytest.mark.asyncio
async def test_executor_returns_false_when_no_pending(
    session_pool: asyncpg.Pool,
    tmp_path: Path,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    storage = RepoStorage(root=tmp_path / "repos")
    indexer = NoOpIndexer(session_pool)
    processed = await execute_next_pending_job(
        config_pool=session_pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
    )
    assert processed is False
