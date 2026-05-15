from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from rag.db.workspace_schema import (
    create_embeddings_table,
    create_workspace_database,
    derive_workspace_dsn,
    drop_workspace_database,
)


@pytest_asyncio.fixture
async def ephemeral_ws_name(pg_container: str) -> AsyncIterator[str]:
    """Yield un nom unique de DB workspace ; drop automatique en teardown."""
    name = f"rag_test_ws_{uuid.uuid4().hex[:10]}"
    yield name
    admin = await asyncpg.connect(pg_container.rsplit("/", 1)[0] + "/postgres")
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


def test_derive_workspace_dsn_replaces_dbname() -> None:
    admin_dsn = "postgresql://rag:pwd@192.168.10.184:5432/postgres"
    assert (
        derive_workspace_dsn(admin_dsn, "rag_harpocrate")
        == "postgresql://rag:pwd@192.168.10.184:5432/rag_harpocrate"
    )


@pytest.mark.asyncio
async def test_create_workspace_database_creates_db(
    pg_container: str, ephemeral_ws_name: str
) -> None:
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    await create_workspace_database(admin_dsn, ephemeral_ws_name)

    admin = await asyncpg.connect(admin_dsn)
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname=$1", ephemeral_ws_name
        )
    finally:
        await admin.close()
    assert exists == 1


@pytest.mark.asyncio
async def test_create_workspace_database_idempotent_raises_already_exists(
    pg_container: str, ephemeral_ws_name: str
) -> None:
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    await create_workspace_database(admin_dsn, ephemeral_ws_name)
    # Second call must raise asyncpg.DuplicateDatabaseError (caller decides retry policy).
    with pytest.raises(asyncpg.DuplicateDatabaseError):
        await create_workspace_database(admin_dsn, ephemeral_ws_name)


@pytest.mark.asyncio
async def test_drop_workspace_database_is_idempotent(
    pg_container: str, ephemeral_ws_name: str
) -> None:
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    # drop avant create : pas d'erreur (IF EXISTS).
    await drop_workspace_database(admin_dsn, ephemeral_ws_name)
    await create_workspace_database(admin_dsn, ephemeral_ws_name)
    await drop_workspace_database(admin_dsn, ephemeral_ws_name)
    await drop_workspace_database(admin_dsn, ephemeral_ws_name)  # double drop OK


@pytest.mark.asyncio
async def test_create_embeddings_table_with_vector_dimension(
    pg_container: str, ephemeral_ws_name: str
) -> None:
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    await create_workspace_database(admin_dsn, ephemeral_ws_name)

    ws_dsn = derive_workspace_dsn(admin_dsn, ephemeral_ws_name)
    await create_embeddings_table(ws_dsn, dimension=1536)

    conn = await asyncpg.connect(ws_dsn)
    try:
        regclass = await conn.fetchval("SELECT to_regclass('public.embeddings')::text")
        assert regclass == "embeddings"

        # Vérifie la dimension du type vector.
        dim_check = await conn.fetchval(
            "SELECT a.atttypmod FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relname = 'embeddings' AND a.attname = 'embedding'"
        )
        assert dim_check == 1536  # atttypmod for vector(N) == N

        # Vérifie l'index ivfflat.
        idx = await conn.fetchval(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename='embeddings' AND indexdef ILIKE '%ivfflat%'"
        )
        assert idx is not None
    finally:
        await conn.close()
