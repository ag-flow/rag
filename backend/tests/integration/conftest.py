from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def migrated(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    """Pool sur une base avec toutes les migrations appliquées et workspaces vides.

    Partagé entre tous les tests d'intégration qui ont besoin du schéma complet
    sans fixtures de données. Chaque test repart d'une base fraîche (scope=function
    via session_pool) avec le schéma prêt.
    """
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool
