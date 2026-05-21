from __future__ import annotations

import re
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import (
    ModelNotSupported,
    RefNotFoundInVault,
    VaultUnreachable,
    WorkspaceAlreadyExists,
)
from rag.db.migrations import run_migrations
from rag.db.workspace_schema import derive_workspace_dsn
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.secrets.resolver import VaultLookupFailed
from rag.services.workspaces import create_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    """Résolveur en mémoire : substitue Harpocrate pour les tests."""

    def __init__(self, known: dict[str, str], *, raise_on: Exception | None = None) -> None:
        self._known = known
        self._raise = raise_on

    async def resolve_with_retry(self, ref: str) -> str:
        if self._raise is not None:
            raise self._raise
        # Le service appelle resolve_with_retry sur ${vault://rag:<logical>}
        m = re.fullmatch(r"\$\{vault://[^:]+:([^}]+)\}", ref)
        assert m, f"Expected vault formalism, got {ref}"
        logical = m.group(1)
        if logical not in self._known:
            raise VaultLookupFailed(f"No secret for {logical}")
        return self._known[logical]


def _make_harpo_service(
    *,
    vault_exists: bool = True,
    secret_store: dict[str, str] | None = None,
) -> MagicMock:
    """Stub HarpocrateVaultsService pour les tests d'intégration."""
    store = secret_store if secret_store is not None else {}
    service = MagicMock()
    if vault_exists:
        vault = MagicMock(spec=VaultSummary)
        vault.id = uuid4()
        vault.base_url = "http://harpo-stub:8200"
        service.get_by_name = AsyncMock(return_value=vault)
    else:
        service.get_by_name = AsyncMock(return_value=None)

    async def _write(_conn, *, vault_name: str, path: str, value: str) -> None:
        store[path] = value

    async def _delete(_conn, *, vault_name: str, path: str) -> None:
        store.pop(path, None)

    service.write_secret = _write
    service.delete_secret = _delete
    return service


def _make_request(name: str = "ws_create_1") -> WorkspaceCreateRequest:
    return WorkspaceCreateRequest(
        name=name,
        api_key_vault="rag",
        indexer=IndexerSpec(
            provider="openai",
            model="text-embedding-3-small",
            api_key_ref="openai_embedding_key",
        ),
    )


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
    """Drop tous les `rag_<name>` créés par les tests de cette session."""
    yield
    import asyncio

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

    asyncio.get_event_loop().run_until_complete(_cleanup())


@pytest.mark.asyncio
async def test_create_workspace_inserts_config_and_creates_db(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    resolver = _StubResolver({"openai_embedding_key": "sk-xxx"})
    store: dict[str, str] = {}
    harpo = _make_harpo_service(secret_store=store)

    req = _make_request(name="ws_create_1")
    resp = await create_workspace(
        request=req,
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=resolver,  # type: ignore[arg-type]
        harpocrate_vaults_service=harpo,
    )

    assert resp["name"] == "ws_create_1"
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", resp["api_key"])

    # L'api_key a été écrite dans Harpocrate via write_secret
    assert "wsapi_ws_create_1" in store
    assert store["wsapi_ws_create_1"] == resp["api_key"]

    # workspaces row inséré — vérifier api_key_ref + api_key_fingerprint
    row = await session_pool.fetchrow(
        "SELECT id, name, rag_base, api_key_ref, api_key_fingerprint "
        "FROM workspaces WHERE name=$1",
        "ws_create_1",
    )
    assert row is not None
    assert row["rag_base"] == "rag_ws_create_1"
    assert "wsapi_ws_create_1" in row["api_key_ref"]
    assert row["api_key_fingerprint"] == sha256(resp["api_key"].encode()).hexdigest()

    # indexer_configs row inséré
    ic = await session_pool.fetchrow(
        "SELECT provider, model, dimension FROM indexer_configs WHERE workspace_id=$1",
        row["id"],
    )
    assert ic is not None
    assert ic["dimension"] == 1536

    # Base physique rag_ws_create_1 existe + table embeddings + index ivfflat
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
    resolver = _StubResolver({"openai_embedding_key": "sk-x"})
    harpo = _make_harpo_service()
    req = _make_request(name="ws_dup")
    await create_workspace(
        request=req,
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=resolver,  # type: ignore[arg-type]
        harpocrate_vaults_service=harpo,
    )

    with pytest.raises(WorkspaceAlreadyExists):
        await create_workspace(
            request=req,
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=resolver,  # type: ignore[arg-type]
            harpocrate_vaults_service=harpo,
        )


@pytest.mark.asyncio
async def test_create_workspace_unknown_model_raises(
    pg_container: str, session_pool: asyncpg.Pool
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    resolver = _StubResolver({"k": "v"})
    harpo = _make_harpo_service()
    req = WorkspaceCreateRequest(
        name="ws_unknown",
        api_key_vault="rag",
        indexer=IndexerSpec(provider="nope", model="nope", api_key_ref="k"),
    )
    with pytest.raises(ModelNotSupported):
        await create_workspace(
            request=req,
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=resolver,  # type: ignore[arg-type]
            harpocrate_vaults_service=harpo,
        )


@pytest.mark.asyncio
async def test_create_workspace_ref_not_in_vault_raises(
    pg_container: str, session_pool: asyncpg.Pool
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    resolver = _StubResolver({})  # aucune clé connue
    harpo = _make_harpo_service()
    req = _make_request("ws_no_ref")
    with pytest.raises(RefNotFoundInVault) as exc_info:
        await create_workspace(
            request=req,
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=resolver,  # type: ignore[arg-type]
            harpocrate_vaults_service=harpo,
        )
    assert exc_info.value.ref == "openai_embedding_key"


@pytest.mark.asyncio
async def test_create_workspace_vault_unreachable_raises(
    pg_container: str, session_pool: asyncpg.Pool
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    resolver = _StubResolver({}, raise_on=ConnectionError("vault down"))
    harpo = _make_harpo_service()
    req = _make_request("ws_vault_down")
    with pytest.raises(VaultUnreachable):
        await create_workspace(
            request=req,
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=resolver,  # type: ignore[arg-type]
            harpocrate_vaults_service=harpo,
        )
