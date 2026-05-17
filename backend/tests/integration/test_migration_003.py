from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_index_jobs_columns(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'index_jobs'"
            )
        }
    expected = {
        "id",
        "workspace_id",
        "source_id",
        "triggered_by",
        "status",
        "files_changed",
        "files_skipped",
        "error_message",
        "started_at",
        "finished_at",
        "duration_ms",
    }
    assert expected.issubset(cols)


@pytest.mark.asyncio
async def test_index_jobs_status_default(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_mig003', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_mig003', 'c', 'b') RETURNING id"
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by) "
            "VALUES ($1, 'manual') RETURNING id",
            ws_id,
        )
        status = await conn.fetchval("SELECT status FROM index_jobs WHERE id = $1", job_id)
        assert status == "pending"
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)


@pytest.mark.asyncio
async def test_index_jobs_invalid_triggered_by_rejected(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_mig003_bad', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_mig003_bad', 'c', 'b') RETURNING id"
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO index_jobs (workspace_id, triggered_by) VALUES ($1, 'invalid')",
                ws_id,
            )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)


@pytest.mark.asyncio
async def test_indexed_documents_unique_ws_path(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('w_mig003b', pgp_sym_encrypt('k', 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'::text)::bytea, 'fp_w_mig003b', 'c', 'b') RETURNING id"
        )
        await conn.execute(
            "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
            "VALUES ($1, 'a.md', 'hash1', 'openai/x')",
            ws_id,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
                "VALUES ($1, 'a.md', 'hash2', 'openai/x')",
                ws_id,
            )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)


@pytest.mark.asyncio
async def test_index_jobs_status_index_exists(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        idx = await conn.fetchval(
            "SELECT indexname FROM pg_indexes WHERE indexname = 'idx_jobs_status_workspace'"
        )
        assert idx == "idx_jobs_status_workspace"
