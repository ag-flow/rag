from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_migration_018_correlation_id_and_push_payloads(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        # correlation_id existe sur index_jobs
        col = await conn.fetchval(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='index_jobs' AND column_name='correlation_id'"
        )
        assert col == "correlation_id"

        # status 'skipped' accepté
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('mig018', 'ref', 'fp', 'c', 'b') RETURNING id"
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'push', 'skipped') RETURNING id",
            ws_id,
        )
        assert job_id is not None

        # push_job_payloads existe et ON DELETE CASCADE fonctionne
        await conn.execute(
            "INSERT INTO push_job_payloads (job_id, path, content) VALUES ($1, 'a.md', 'hi')",
            job_id,
        )
        await conn.execute("DELETE FROM index_jobs WHERE id=$1", job_id)
        count = await conn.fetchval(
            "SELECT count(*) FROM push_job_payloads WHERE job_id=$1", job_id
        )
        assert count == 0
