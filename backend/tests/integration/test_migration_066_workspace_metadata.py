from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspace_metadata_columns_exist(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r
            for r in await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns WHERE table_name = 'workspaces'"
            )
        }

    assert "label" in cols
    assert cols["label"]["data_type"] == "text"
    assert "description" in cols
    assert cols["description"]["data_type"] == "text"
    # description NOT NULL DEFAULT '' ; label reste nullable (backfill au besoin).
    assert cols["description"]["is_nullable"] == "NO"


@pytest.mark.asyncio
async def test_backfill_label_equals_name_for_existing(session_pool: asyncpg.Pool) -> None:
    """Un workspace inséré sans label doit obtenir label=name (migration idempotente
    ré-appliquée : le backfill ne touche que les lignes label IS NULL)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO workspaces (name, label, rag_cnx, rag_base) "
            "VALUES ('ws_backfill', NULL, 'postgresql://t/c', 'rag_ws_backfill')"
        )
        # Rejoue le backfill de la migration 066.
        await conn.execute("UPDATE workspaces SET label = name WHERE label IS NULL")
        row = await conn.fetchrow(
            "SELECT name, label, description FROM workspaces WHERE name = 'ws_backfill'"
        )

    assert row is not None
    assert row["label"] == "ws_backfill"
    assert row["description"] == ""


@pytest.mark.asyncio
async def test_name_untouched_by_migration(session_pool: asyncpg.Pool) -> None:
    """La colonne `name` (slug/identifiant) reste présente et inchangée."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        col = await conn.fetchrow(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'workspaces' AND column_name = 'name'"
        )

    assert col is not None
    assert col["data_type"] == "text"
    assert col["is_nullable"] == "NO"
