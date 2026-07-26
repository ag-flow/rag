"""Job de réindexation sans source (`reindex_chunking_change`…) : fan-out en
jobs par source git + re-chunk des documents poussés depuis le stockage
source, via `execute_next_pending_job` (fiche bug aced5d5e)."""

from __future__ import annotations

import json
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.protocol import IndexOutcome, StoredSourceDocument
from rag.sync.executor import execute_next_pending_job
from rag.sync.repo_storage import RepoStorage
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        return "tok"


class _StubClientProvider:
    async def get_default_vault_name(self) -> str | None:
        return "rag"


class _StubIndexer:
    """Indexeur factice : sources stockées injectées, indexations enregistrées."""

    def __init__(self, stored: list[StoredSourceDocument] | None = None) -> None:
        self._stored = stored or []
        self.indexed_paths: list[str] = []

    async def index_file(self, **kwargs: object) -> IndexOutcome:
        self.indexed_paths.append(str(kwargs["path"]))
        return IndexOutcome(chunks=1, strategy=None)

    async def delete_file(self, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("delete_file ne doit pas être appelé")

    async def stored_sources(self, **kwargs: object) -> list[StoredSourceDocument]:
        return self._stored


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


async def _seed_ws(pool: asyncpg.Pool, name: str) -> str:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=name)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
    return ws_id


async def _seed_reindex_job(pool: asyncpg.Pool, ws_id: str) -> str:
    return await pool.fetchval(
        "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
        "VALUES ($1, 'reindex_chunking_change', 'pending') RETURNING id",
        ws_id,
    )


async def _run(pool: asyncpg.Pool, indexer: _StubIndexer, tmp_path: Path) -> bool:
    return await execute_next_pending_job(
        config_pool=pool,
        storage=RepoStorage(tmp_path),
        indexer=indexer,
        resolver=_StubResolver(),
        client_provider=_StubClientProvider(),
    )


@pytest.mark.asyncio
async def test_fan_out_creates_one_pending_job_per_git_source(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    ws_id = await _seed_ws(pool, "ws_reindex_fanout")
    async with pool.acquire() as conn:
        src_ids = [
            await conn.fetchval(
                "INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at) "
                "VALUES ($1, 'git', $2::jsonb, NULL) RETURNING id",
                ws_id,
                json.dumps({"url": f"https://github.com/x/repo{i}", "branch": "main"}),
            )
            for i in range(2)
        ]
    job_id = await _seed_reindex_job(pool, ws_id)

    assert await _run(pool, _StubIndexer(), tmp_path) is True

    status = await pool.fetchval("SELECT status FROM index_jobs WHERE id=$1", job_id)
    assert status == "done"
    children = await pool.fetch(
        "SELECT source_id, triggered_by, status FROM index_jobs "
        "WHERE workspace_id=$1 AND source_id IS NOT NULL",
        ws_id,
    )
    assert {str(c["source_id"]) for c in children} == {str(s) for s in src_ids}
    assert all(c["triggered_by"] == "reindex_chunking_change" for c in children)
    assert all(c["status"] == "pending" for c in children)

    # Un second job de reindex ne crée PAS de doublons (garde pending/running).
    await _seed_reindex_job(pool, ws_id)
    assert await _run(pool, _StubIndexer(), tmp_path) is True
    count = await pool.fetchval(
        "SELECT COUNT(*) FROM index_jobs WHERE workspace_id=$1 AND source_id IS NOT NULL",
        ws_id,
    )
    assert int(count) == 2


@pytest.mark.asyncio
async def test_rechunks_stored_documents_and_skips_unchanged(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    ws_id = await _seed_ws(pool, "ws_reindex_stored")
    async with pool.acquire() as conn:
        # deja.md : dédup identique (hash + indexeur) → skip attendu.
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'deja.md', 'sha256:same', 'openai/text-embedding-3-small')",
            ws_id,
        )
    stored = [
        StoredSourceDocument(
            path="deja.md",
            content="inchangé",
            content_hash="sha256:same",
            title=None,
            source_url=None,
        ),
        StoredSourceDocument(
            path="a-refaire.md",
            content="nouveau contenu",
            content_hash="sha256:new",
            title="T",
            source_url=None,
        ),
    ]
    job_id = await _seed_reindex_job(pool, ws_id)
    indexer = _StubIndexer(stored)

    assert await _run(pool, indexer, tmp_path) is True

    assert indexer.indexed_paths == ["a-refaire.md"]
    row = await pool.fetchrow(
        "SELECT status, files_changed, files_skipped, params FROM index_jobs WHERE id=$1",
        job_id,
    )
    assert row["status"] == "done"
    assert row["files_changed"] == 1
    assert row["files_skipped"] == 1
    params = row["params"] if isinstance(row["params"], dict) else json.loads(row["params"])
    assert params["fanout_sources"] == 0
    assert params["failed_files"] == []
