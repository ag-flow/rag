from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
def admin_dsn() -> str:
    """DSN admin pour créer/supprimer des bases workspace de test.

    Utilise les mêmes env vars que la fixture session_pool. Skip explicite si
    TEST_POSTGRES_PASSWORD est absent.
    """
    host = os.environ.get("TEST_POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("TEST_POSTGRES_PORT", "5432")
    user = os.environ.get("TEST_POSTGRES_USER", "rag")
    pwd = os.environ.get("TEST_POSTGRES_PASSWORD")
    if not pwd:
        pytest.skip(
            "TEST_POSTGRES_PASSWORD non défini — tests workspace skip.",
            allow_module_level=False,
        )
    return f"postgresql://{user}:{pwd}@{host}:{port}/postgres"


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
