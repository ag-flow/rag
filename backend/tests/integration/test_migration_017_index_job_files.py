from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_index_job_files_columns(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'index_job_files'"
            )
        }
    assert {"id", "job_id", "path", "change_type"}.issubset(cols.keys())
    assert cols["job_id"] == "uuid"


@pytest.mark.asyncio
async def test_index_job_files_check_change_type(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        job_id = await _seed_job(conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO index_job_files (job_id, path, change_type) "
                "VALUES ($1, 'x.md', 'renamed')",
                job_id,
            )


@pytest.mark.asyncio
async def test_index_job_files_cascade_on_job_delete(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        job_id = await _seed_job(conn)
        await conn.execute(
            "INSERT INTO index_job_files (job_id, path, change_type) "
            "VALUES ($1, 'a.md', 'added')",
            job_id,
        )
        await conn.execute("DELETE FROM index_jobs WHERE id=$1", job_id)
        n = await conn.fetchval(
            "SELECT count(*) FROM index_job_files WHERE job_id=$1", job_id
        )
    assert n == 0


async def _seed_job(conn: asyncpg.Connection) -> str:
    from hashlib import sha256

    dek = "x" * 32
    api_key = "mig017"
    fp = sha256(api_key.encode()).hexdigest()
    ws_id = await conn.fetchval(
        "INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) "
        "VALUES ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, 'c', 'b') RETURNING id",
        "ws_mig017", api_key, dek, fp,
    )
    return await conn.fetchval(
        "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
        "VALUES ($1, 'manual', 'done') RETURNING id",
        ws_id,
    )
