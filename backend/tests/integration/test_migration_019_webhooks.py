from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_migration_019_webhooks_tables_exist(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await conn.fetchval(
            "INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base) "
            "VALUES ('mig019', 'ref', 'fp', 'c', 'b') RETURNING id"
        )
        wh_id = await conn.fetchval(
            "INSERT INTO workspace_webhooks (workspace_id, name, url) "
            "VALUES ($1, 'hook', 'https://example.com/hook') RETURNING id",
            ws_id,
        )
        assert wh_id is not None

        hdr_id = await conn.fetchval(
            "INSERT INTO webhook_headers (webhook_id, name, value) "
            "VALUES ($1, 'X-Api-Key', 'secret') RETURNING id",
            wh_id,
        )
        assert hdr_id is not None

        # CASCADE sur workspace suppression
        await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_id)
        wh = await conn.fetchval(
            "SELECT id FROM workspace_webhooks WHERE id=$1", wh_id
        )
        assert wh is None
