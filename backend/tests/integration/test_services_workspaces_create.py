from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import ModelNotSupported, WorkspaceAlreadyExists
from rag.db.migrations import run_migrations
from rag.db.workspace_schema import derive_workspace_dsn
from rag.schemas.admin import IndexerCreateSpec, WorkspaceCreateResolved
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.services.workspaces import create_workspace

# NB : les tests historiques "ref absente du coffre" / "coffre injoignable" ont
# été supprimés — depuis le chantier endpoints (cac2b8e), create_workspace ne
# valide plus l'api_key_ref indexeur via le resolver (la ref pointe une
# provider_api_key existante, validée en amont par le router).

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    """Résolveur en mémoire : le service ne l'utilise que pour le rerank."""

    async def resolve_with_retry(self, ref: str) -> str:
        return "sk-stub"


def _make_harpo_service() -> MagicMock:
    """Stub HarpocrateVaultsService : un coffre par défaut 'rag' existe.

    `get_default` est vérifié par create_workspace AVANT tout DDL — il doit
    être un AsyncMock (le service l'await).
    """
    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    vault.name = "rag"
    vault.base_url = "http://harpo-stub:8200"
    service.get_by_name = AsyncMock(return_value=vault)
    service.get_default = AsyncMock(return_value=vault)
    return service


def _make_request(name: str = "ws_create_1") -> WorkspaceCreateResolved:
    return WorkspaceCreateResolved(
        name=name,
        label=name,
        indexer=IndexerCreateSpec(
            provider="openai",
            model="text-embedding-3-small",
            api_key_ref="openai_embedding_key",
        ),
    )


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
    """Drop tous les `rag_ws_*` créés par les tests de cette session."""
    yield

    async def _cleanup() -> None:
        admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
        admin = await asyncpg.connect(admin_dsn)
        try:
            rows = await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'rag_ws_%'"
            )
            for r in rows:
                await admin.execute(f'DROP DATABASE IF EXISTS "{r["datname"]}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.run(_cleanup())


@pytest.mark.asyncio
async def test_create_workspace_inserts_config_and_creates_db(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    resp = await create_workspace(
        request=_make_request(name="ws_create_1"),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
    )

    # Plus de clé API à la création : {id, name, label, description, created_at}
    # (les clés d'accès se créent au niveau utilisateur, cf. user_api_keys)
    assert resp["name"] == "ws_create_1"
    assert set(resp) == {"id", "name", "label", "description", "created_at"}

    # workspaces row inséré
    row = await session_pool.fetchrow(
        "SELECT id, name, rag_base FROM workspaces WHERE name=$1", "ws_create_1"
    )
    assert row is not None
    assert row["rag_base"] == "rag_ws_create_1"
    assert str(row["id"]) == resp["id"]

    # indexer_configs row inséré avec la dimension du modèle
    ic = await session_pool.fetchrow(
        "SELECT provider, model, dimension FROM indexer_configs WHERE workspace_id=$1",
        row["id"],
    )
    assert ic is not None
    assert ic["dimension"] == 1536

    # chunking_configs par défaut inséré
    cc = await session_pool.fetchrow(
        "SELECT strategy FROM chunking_configs WHERE workspace_id=$1", row["id"]
    )
    assert cc is not None
    assert cc["strategy"] == "paragraph"

    # Base physique rag_ws_create_1 existe + table embeddings provisionnée
    admin = await asyncpg.connect(admin_dsn)
    try:
        present = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname='rag_ws_create_1'")
    finally:
        await admin.close()
    assert present == 1

    ws_dsn = derive_workspace_dsn(admin_dsn, "rag_ws_create_1")
    ws_conn = await asyncpg.connect(ws_dsn)
    try:
        regclass = await ws_conn.fetchval("SELECT to_regclass('public.embeddings')::text")
    finally:
        await ws_conn.close()
    assert regclass == "embeddings"


@pytest.mark.asyncio
async def test_create_workspace_duplicate_name_raises(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    harpo = _make_harpo_service()
    req = _make_request(name="ws_dup")
    await create_workspace(
        request=req,
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_StubResolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=harpo,
    )

    with pytest.raises(WorkspaceAlreadyExists):
        await create_workspace(
            request=req,
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=_StubResolver(),  # type: ignore[arg-type]
            harpocrate_vaults_service=harpo,
        )


@pytest.mark.asyncio
async def test_create_workspace_unknown_model_raises(
    pg_container: str, session_pool: asyncpg.Pool
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    req = WorkspaceCreateResolved(
        name="ws_unknown",
        label="ws_unknown",
        indexer=IndexerCreateSpec(provider="nope", model="nope", api_key_ref="k"),
    )
    with pytest.raises(ModelNotSupported):
        await create_workspace(
            request=req,
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=_StubResolver(),  # type: ignore[arg-type]
            harpocrate_vaults_service=_make_harpo_service(),
        )
