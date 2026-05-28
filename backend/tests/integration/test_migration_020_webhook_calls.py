from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_migration_020_webhook_calls_table(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('mig020', 'ref', 'fp', 'c', 'b') RETURNING id"
        )
        job_id = await conn.fetchval(
            "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
            "VALUES ($1, 'push', 'done') RETURNING id",
            ws_id,
        )
        wh_id = await conn.fetchval(
            "INSERT INTO workspace_webhooks (workspace_id, name, url) "
            "VALUES ($1, 'h', 'https://x.com') RETURNING id",
            ws_id,
        )
        call_id = await conn.fetchval(
            """
            INSERT INTO webhook_calls
                (workspace_id, webhook_id, job_id, correlation_id, triggered_by, webhook_url, http_status, duration_ms)
            VALUES ($1, $2, $3, 'corr-123', 'push', 'https://x.com', 200, 42)
            RETURNING id
            """,
            ws_id, wh_id, job_id,
        )
        assert call_id is not None

        # Les index existent
        idx = await conn.fetchval(
            "SELECT indexname FROM pg_indexes WHERE indexname='idx_webhook_calls_purge'"
        )
        assert idx == "idx_webhook_calls_purge"
