from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.indexer.noop import NoOpIndexer
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


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


async def _seed_push_job(
    pool: asyncpg.Pool, ws_name: str, path: str, content: str
) -> tuple[str, str]:
    """Seed workspace + push job. Returns (job_id, correlation_id)."""
    correlation_id = "corr-test-001"
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name=ws_name)
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'push', 'pending', $2) RETURNING id",
            ws_id,
            correlation_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, $2, $3)",
            job_id,
            path,
            content,
        )
    return str(job_id), correlation_id


@pytest.mark.asyncio
async def test_push_job_executed_done(pool: asyncpg.Pool, tmp_path: Path) -> None:
    storage = RepoStorage(tmp_path)
    indexer = NoOpIndexer(pool)
    job_id, _ = await _seed_push_job(pool, "ws_push1", "a.md", "hello world")

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )
    assert result is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM index_jobs WHERE id=$1::uuid", job_id
        )
        assert row["status"] == "done"

        payload = await conn.fetchval(
            "SELECT job_id FROM push_job_payloads WHERE job_id=$1::uuid", job_id
        )
        assert payload is None  # cleaned up


@pytest.mark.asyncio
async def test_push_job_skipped_when_same_hash(pool: asyncpg.Pool, tmp_path: Path) -> None:
    storage = RepoStorage(tmp_path)
    indexer = NoOpIndexer(pool)

    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_push2")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        content = "same content"
        content_hash = "sha256:" + sha256(content.encode()).hexdigest()
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'a.md', $2, 'openai/text-embedding-3-small')",
            ws_id,
            content_hash,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'push', 'pending', 'corr-002') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, 'a.md', $2)",
            job_id,
            content,
        )

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )
    assert result is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status FROM index_jobs WHERE id=$1", job_id
        )
        assert row["status"] == "skipped"


@pytest.mark.asyncio
async def test_reindex_force_bypasses_skip_same_hash(pool: asyncpg.Pool, tmp_path: Path) -> None:
    """Ré-évaluation : `force=true` re-indexe même à contenu/indexeur identiques."""
    storage = RepoStorage(tmp_path)
    indexer = NoOpIndexer(pool)

    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_reindex1")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        content = "same content"
        content_hash = "sha256:" + sha256(content.encode()).hexdigest()
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'a.md', $2, 'openai/text-embedding-3-small')",
            ws_id,
            content_hash,
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'reindex_document', 'pending', 'corr-reidx') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content, force) "
            "VALUES ($1, 'a.md', $2, true)",
            job_id,
            content,
        )

    result = await execute_next_pending_job(
        config_pool=pool,
        storage=storage,
        indexer=indexer,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )
    assert result is True

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status FROM index_jobs WHERE id=$1", job_id)
        # Pas 'skipped' : le force a court-circuité le dedup → ré-indexation.
        assert row["status"] == "done"


async def _run_once(pool: asyncpg.Pool, tmp_path: Path) -> None:
    await execute_next_pending_job(
        config_pool=pool,
        storage=RepoStorage(tmp_path),
        indexer=NoOpIndexer(pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )


@pytest.mark.asyncio
async def test_execution_records_outcome_in_job_params(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """Après exécution, le job porte la stratégie effective et le nb de chunks
    (observabilité « demandé vs exécuté » — NoOp : 1 chunk, stratégie None)."""
    job_id, _ = await _seed_push_job(pool, "ws_outcome", "a.md", "hello")

    await execute_next_pending_job(
        config_pool=pool,
        storage=RepoStorage(tmp_path),
        indexer=NoOpIndexer(pool),
        resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        webhook_secret=None,
    )

    async with pool.acquire() as conn:
        raw = await conn.fetchval(
            "SELECT params FROM index_jobs WHERE id=$1::uuid", job_id
        )
    import json

    params = json.loads(raw)
    assert params["chunks_created"] == 1
    assert params["executed_strategy"] is None  # NoOp n'a pas de stratégie


@pytest.mark.asyncio
async def test_source_url_persisted_and_preserved_on_reindex(
    pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """L'URL fournie au push atterrit dans indexed_documents ; un re-index sans
    URL ne l'efface pas (COALESCE : last non-null gagne)."""
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_srcurl")
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 1536)",
            ws_id,
        )
        job1 = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'push', 'pending', 'c1') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content, source_url) "
            "VALUES ($1, 'a.md', 'v1', 'https://docs.example/a?token=xyz')",
            job1,
        )

    await _run_once(pool, tmp_path)

    async with pool.acquire() as conn:
        url = await conn.fetchval(
            "SELECT source_url FROM indexed_documents WHERE workspace_id=$1 AND path='a.md'",
            ws_id,
        )
        assert url == "https://docs.example/a?token=xyz"

        # Re-index SANS source_url (force pour bypasser le dedup).
        job2 = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status, correlation_id) "
            "VALUES ($1, 'reindex_document', 'pending', 'c2') RETURNING id",
            ws_id,
        )
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content, force) "
            "VALUES ($1, 'a.md', 'v2', true)",
            job2,
        )

    await _run_once(pool, tmp_path)

    async with pool.acquire() as conn:
        url = await conn.fetchval(
            "SELECT source_url FROM indexed_documents WHERE workspace_id=$1 AND path='a.md'",
            ws_id,
        )
        # Préservée malgré le re-index sans URL.
        assert url == "https://docs.example/a?token=xyz"
