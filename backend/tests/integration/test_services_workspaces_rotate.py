from __future__ import annotations

import re
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache
from rag.db.helpers import fetch_one
from rag.db.migrations import run_migrations
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.services.workspaces import create_workspace, rotate_apikey

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _Resolver:
    async def resolve_with_retry(self, ref: str) -> str:
        assert re.fullmatch(r"\$\{vault://[^:]+:[^}]+\}", ref)
        return "sk-x"


def _make_harpo_service(
    secret_store: dict[str, str] | None = None,
) -> MagicMock:
    """Stub HarpocrateVaultsService pour les tests d'intégration."""
    store = secret_store if secret_store is not None else {}
    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    service.get_by_name = AsyncMock(return_value=vault)

    async def _write(_conn, *, vault_name: str, path: str, value: str) -> None:
        store[path] = value

    async def _delete(_conn, *, vault_name: str, path: str) -> None:
        store.pop(path, None)

    service.write_secret = _write
    service.delete_secret = _delete
    return service


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
    yield
    import asyncio

    async def _cleanup() -> None:
        admin = await asyncpg.connect(pg_container.rsplit("/", 1)[0] + "/postgres")
        try:
            for r in await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'rag_ws_%'"
            ):
                await admin.execute(f'DROP DATABASE IF EXISTS "{r["datname"]}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.get_event_loop().run_until_complete(_cleanup())


@pytest.mark.asyncio
async def test_rotate_apikey_returns_new_key_and_updates_db(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    store: dict[str, str] = {}
    harpo = _make_harpo_service(store)

    create_resp = await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_rotate",
            api_key_vault="rag",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=harpo,
    )
    old_key = create_resp["api_key"]
    assert store.get("wsapi_ws_rotate") == old_key

    result = await rotate_apikey(
        name="ws_rotate",
        config_pool=session_pool,
        harpocrate_vaults_service=harpo,
        apikey_cache=ApiKeyCache(),
    )
    new_key = result["api_key"]
    assert new_key != old_key
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", new_key)

    # Harpocrate a bien la nouvelle valeur
    assert store.get("wsapi_ws_rotate") == new_key

    row = await fetch_one(
        session_pool,
        "SELECT api_key_fingerprint FROM workspaces WHERE name=$1",
        "ws_rotate",
    )
    assert row is not None
    assert row["api_key_fingerprint"] == sha256(new_key.encode()).hexdigest()
    # L'ancienne clé ne correspond plus au fingerprint
    assert row["api_key_fingerprint"] != sha256(old_key.encode()).hexdigest()


@pytest.mark.asyncio
async def test_rotate_apikey_workspace_not_found(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    harpo = _make_harpo_service()
    with pytest.raises(WorkspaceNotFound):
        await rotate_apikey(
            name="absent",
            config_pool=session_pool,
            harpocrate_vaults_service=harpo,
            apikey_cache=ApiKeyCache(),
        )


@pytest.mark.asyncio
async def test_rotate_handles_fingerprint_collision(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    """La boucle anti-collision gère le cas où la clé générée a un fingerprint déjà pris.

    Scénario : generate_api_key retourne "k_collide" les 2 premières fois,
    puis "k_ok" (fingerprint distinct). Un workspace tiers possède déjà le
    fingerprint de "k_collide". rotate_apikey ne doit pas lever et doit
    retourner "k_ok".
    """
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    harpo = _make_harpo_service()

    # Workspace cible de la rotation
    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_col_target",
            api_key_vault="rag",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=harpo,
    )

    # Workspace tiers dont le fingerprint = sha256("k_collide")
    # On l'insère directement avec seed_workspace pour éviter la création de BDD
    from tests.integration._workspace_seed import seed_workspace
    async with session_pool.acquire() as conn:
        await seed_workspace(
            conn,
            name="ws_col_blocker",
            api_key="k_collide",
            rag_cnx="postgresql://test/blocker",
            rag_base="rag_test_blocker",
        )

    keys_iter = iter(["k_collide", "k_collide", "k_ok"])
    with patch("rag.services.workspaces.generate_api_key", side_effect=lambda: next(keys_iter)):
        result = await rotate_apikey(
            name="ws_col_target",
            config_pool=session_pool,
            harpocrate_vaults_service=harpo,
            apikey_cache=ApiKeyCache(),
        )

    assert result["api_key"] == "k_ok"
    row = await fetch_one(
        session_pool,
        "SELECT api_key_fingerprint FROM workspaces WHERE name=$1",
        "ws_col_target",
    )
    assert row is not None
    assert row["api_key_fingerprint"] == sha256("k_ok".encode()).hexdigest()
