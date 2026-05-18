from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

from rag.db.migrations import run_migrations
from rag.db.workspace_schema import derive_workspace_dsn
from tests.conftest import _admin_dsn

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
def admin_dsn() -> str:
    """DSN admin pour créer/supprimer des bases workspace de test.

    Délègue à `tests.conftest._admin_dsn` (source de vérité unique : même
    parsing d'env vars et même skip si TEST_POSTGRES_PASSWORD est absent que
    le reste des tests d'intégration). On accepte l'import d'un nom privé
    inter-conftests plutôt que de dupliquer la logique et risquer la dérive.
    """
    return _admin_dsn()


@pytest_asyncio.fixture
async def workspace_test_db(admin_dsn: str) -> AsyncIterator[tuple[str, str]]:
    """Provisionne une base workspace de test isolée. Yield (dbname, dsn).

    Le nom est UUID-suffixé pour éviter les collisions entre runs concurrents.
    La base est droppée dans le `finally` — les tests n'ont plus à gérer le
    cleanup eux-mêmes.
    """
    name = f"rag_wsm_{uuid.uuid4().hex[:12]}"
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
    dsn = derive_workspace_dsn(admin_dsn, name)
    try:
        yield name, dsn
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


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
