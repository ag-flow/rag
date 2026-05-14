from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    return asyncio.DefaultEventLoopPolicy()


def _admin_dsn() -> str:
    """DSN admin (base `postgres`) du Postgres de test.

    Aligné CLAUDE.md : « tests connectés à un Postgres + pgvector hébergés
    sur l'infra LXC ». Défaut = LXC 303 ; le password DOIT être fourni via
    TEST_POSTGRES_PASSWORD (pas de défaut, on échoue explicitement).
    """
    host = os.environ.get("TEST_POSTGRES_HOST", "192.168.10.184")
    port = os.environ.get("TEST_POSTGRES_PORT", "5432")
    user = os.environ.get("TEST_POSTGRES_USER", "rag")
    pwd = os.environ.get("TEST_POSTGRES_PASSWORD")
    if not pwd:
        pytest.skip(
            "TEST_POSTGRES_PASSWORD non défini — tests d'intégration sautés. "
            "Cf. backend/README.md.",
            allow_module_level=False,
        )
    return f"postgresql://{user}:{pwd}@{host}:{port}/postgres"


def _replace_dbname(dsn: str, dbname: str) -> str:
    return dsn.rsplit("/", 1)[0] + f"/{dbname}"


@pytest_asyncio.fixture
async def pg_container() -> AsyncIterator[str]:
    """Provisionne une base test jetable sur le Postgres partagé et yield son DSN.

    **Scope function** : chaque test obtient sa propre base `rag_test_<uuid>`
    pour garantir une isolation totale. Les tests d'intégration des migrations
    droppent et recréent partiellement le schéma — sans isolation, l'ordre
    d'exécution introduit des conflits sur les tables non droppées.

    Le nom `pg_container` est conservé pour la stabilité des call-sites
    historiques (la fixture spawnait un container testcontainers avant le
    refactor T18.9). Désormais elle s'appuie sur le Postgres de l'infra de
    dev (LXC 303 par défaut).
    """
    admin_dsn = _admin_dsn()
    dbname = f"rag_test_{uuid.uuid4().hex[:12]}"
    db_dsn = _replace_dbname(admin_dsn, dbname)

    conn = await asyncpg.connect(admin_dsn)
    try:
        # `dbname` est généré localement (uuid.uuid4) — pas d'entrée externe.
        # asyncpg n'accepte pas de paramètre bindé pour un identifiant DDL.
        await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()

    conn = await asyncpg.connect(db_dsn)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await conn.close()

    try:
        yield db_dsn
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest_asyncio.fixture
async def session_pool(pg_container: str) -> AsyncIterator[asyncpg.Pool]:
    """Pool asyncpg sur la base test jetable du test courant (function scope).

    Le nom historique `session_pool` est conservé pour la stabilité des
    call-sites — il ne s'agit plus d'un pool session-scopé depuis le
    refactor T18.9.
    """
    pool = await asyncpg.create_pool(pg_container, min_size=1, max_size=4)
    try:
        yield pool
    finally:
        await pool.close()
