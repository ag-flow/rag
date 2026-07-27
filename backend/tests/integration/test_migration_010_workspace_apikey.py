"""Migration 010 (api_key chiffrée par workspace) — feature RETIRÉE depuis.

Historique : 010 a introduit api_key_encrypted/api_key_fingerprint sur
`workspaces`, 015 a remplacé le chiffrement par une référence Harpocrate
(api_key_ref), 033 a déplacé les clés vers `workspace_api_keys` et purgé les
colonnes, puis 053 a droppé `workspace_api_keys` au profit de `user_api_keys`.

À HEAD on n'asserte donc plus le round-trip pgcrypto ni l'index fingerprint :
on vérifie la DISPARITION complète de l'ancien modèle (les tests positifs du
modèle actuel vivent dans test_migration_053.py).
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.mark.asyncio
async def test_workspaces_apikey_columns_removed(session_pool: asyncpg.Pool) -> None:
    """Aucune colonne api_key_* ne subsiste sur workspaces (010→015→033)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'workspaces'"
            )
        }
    assert not {c for c in cols if c.startswith("api_key")}


@pytest.mark.asyncio
async def test_apikey_fingerprint_index_removed(session_pool: asyncpg.Pool) -> None:
    """L'index unique sur le fingerprint est tombé avec la colonne (033)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'workspaces' AND indexname = $1",
            "idx_workspaces_apikey_fingerprint",
        )
    assert row is None


@pytest.mark.asyncio
async def test_workspace_api_keys_table_dropped(session_pool: asyncpg.Pool) -> None:
    """workspace_api_keys (033) a été droppée en 053, remplacée par user_api_keys."""
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        tables = {
            r["table_name"]
            for r in await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name IN ('workspace_api_keys', 'user_api_keys')"
            )
        }
    assert "workspace_api_keys" not in tables
    assert "user_api_keys" in tables
