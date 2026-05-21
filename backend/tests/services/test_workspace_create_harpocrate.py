from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import (
    HarpocrateWriteFailed,
    VaultNotFoundForWorkspace,
    WorkspaceAlreadyExists,
)
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.services.workspaces import create_workspace


def _make_request(name: str = "test1", vault: str = "rag") -> WorkspaceCreateRequest:
    """Construit une requête valide minimale (Ollama, sans api_key_ref)."""
    return WorkspaceCreateRequest(
        name=name,
        api_key_vault=vault,
        indexer=IndexerSpec(
            provider="ollama",
            model="mxbai-embed-large",
            api_key_ref=None,
            base_url="http://ollama:11434",
        ),
    )


def _make_harpo_service(
    *,
    vault_exists: bool = True,
    write_raises: Exception | None = None,
) -> MagicMock:
    """Stub minimal de HarpocrateVaultsService."""

    from rag.schemas.harpocrate_vaults import VaultSummary

    harpo = MagicMock()
    if vault_exists:
        vault = MagicMock(spec=VaultSummary)
        vault.id = uuid4()
        vault.base_url = "http://harpocrate:8200"
        harpo.get_by_name = AsyncMock(return_value=vault)
        harpo.reveal_api_key = AsyncMock(return_value="tok-test")
    else:
        harpo.get_by_name = AsyncMock(return_value=None)

    if write_raises is not None:
        harpo.write_secret = AsyncMock(side_effect=write_raises)
    else:
        harpo.write_secret = AsyncMock(return_value=None)

    harpo.delete_secret = AsyncMock(return_value=None)
    return harpo


def _make_stub_pool() -> MagicMock:
    """Stub asyncpg.Pool minimal — acquire() retourne un context manager."""
    pool = MagicMock(spec=asyncpg.Pool)
    conn = AsyncMock()
    # Simule `async with pool.acquire() as conn:`
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


# ---------------------------------------------------------------------------
# Test 1 — vault manquant → VaultNotFoundForWorkspace AVANT toute écriture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workspace_with_missing_vault_raises_vault_not_found() -> None:
    """Si le coffre n'existe pas, VaultNotFoundForWorkspace levé avant write_secret."""
    harpo = _make_harpo_service(vault_exists=False)
    pool = _make_stub_pool()
    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(return_value="unused")
    request = _make_request(vault="missing-vault")

    with (
        patch("rag.services.workspaces.get_dimension_or_raise", new=AsyncMock(return_value=1024)),
        pytest.raises(VaultNotFoundForWorkspace),
    ):
        await create_workspace(
            request=request,
            config_pool=pool,
            admin_dsn="postgresql://stub",
            resolver=resolver,
            harpocrate_vaults_service=harpo,
        )

    harpo.write_secret.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2 — chemin nominal → write_secret appelé avec le bon path + ref retournée
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workspace_writes_to_harpocrate_under_wsapi_path_returns_full_ref() -> None:
    """write_secret est appelé avec path=wsapi_<name>, retour contient api_key_ref."""
    harpo = _make_harpo_service(vault_exists=True)
    pool = _make_stub_pool()
    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(return_value="unused")

    ws_id = uuid4()
    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, k: ws_id if k == "id" else MagicMock()

    # Stub transaction(config_pool) : context manager qui retourne une conn
    conn_in_tx = AsyncMock()
    conn_in_tx.fetchrow = AsyncMock(return_value=fake_row)
    conn_in_tx.execute = AsyncMock(return_value=None)

    with (
        patch("rag.services.workspaces.get_dimension_or_raise", new=AsyncMock(return_value=1024)),
        patch(
            "rag.services.workspaces.transaction",
        ) as mock_tx,
        patch("rag.services.workspaces.create_workspace_database", new=AsyncMock()),
        patch("rag.services.workspaces.create_embeddings_table", new=AsyncMock()),
        patch("rag.services.workspaces.apply_pending", new=AsyncMock()),
    ):
        mock_tx.return_value.__aenter__ = AsyncMock(return_value=conn_in_tx)
        mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

        resp = await create_workspace(
            request=_make_request(name="myws", vault="rag"),
            config_pool=pool,
            admin_dsn="postgresql://stub",
            resolver=resolver,
            harpocrate_vaults_service=harpo,
        )

    # write_secret a bien été appelé avec path=wsapi_myws dans le coffre "rag"
    harpo.write_secret.assert_called_once()
    call_kwargs = harpo.write_secret.call_args.kwargs
    assert call_kwargs["vault_name"] == "rag"
    assert call_kwargs["path"] == "wsapi_myws"

    # La réponse contient l'api_key_ref construite
    assert "api_key_ref" in resp
    assert "rag" in resp["api_key_ref"]
    assert "wsapi_myws" in resp["api_key_ref"]

    # api_key en clair présent
    assert "api_key" in resp
    assert resp["api_key"]


# ---------------------------------------------------------------------------
# Test 3 — échec write Harpocrate → HarpocrateWriteFailed propagé, pas d'INSERT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workspace_harpocrate_write_failure_raises_before_insert() -> None:
    """Si write_secret lève HarpocrateWriteFailed, on ne doit pas insérer en DB."""
    harpo = _make_harpo_service(
        vault_exists=True,
        write_raises=HarpocrateWriteFailed("réseau coupé"),
    )
    pool = _make_stub_pool()
    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(return_value="unused")

    conn_in_tx = AsyncMock()
    conn_in_tx.fetchrow = AsyncMock(return_value=MagicMock())
    conn_in_tx.execute = AsyncMock(return_value=None)

    with (
        patch("rag.services.workspaces.get_dimension_or_raise", new=AsyncMock(return_value=1024)),
        patch("rag.services.workspaces.transaction") as mock_tx,
        pytest.raises(HarpocrateWriteFailed),
    ):
        mock_tx.return_value.__aenter__ = AsyncMock(return_value=conn_in_tx)
        mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

        await create_workspace(
            request=_make_request(name="fail-ws", vault="rag"),
            config_pool=pool,
            admin_dsn="postgresql://stub",
            resolver=resolver,
            harpocrate_vaults_service=harpo,
        )

    # La transaction DB ne doit pas avoir été démarrée
    mock_tx.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 — rollback Harpocrate si INSERT DB lève UniqueViolationError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_workspace_db_failure_triggers_harpocrate_delete_secret() -> None:
    """Sur UniqueViolationError en INSERT, delete_secret est appelé (rollback Harpocrate)."""
    harpo = _make_harpo_service(vault_exists=True)
    pool = _make_stub_pool()
    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(return_value="unused")

    conn_in_tx = AsyncMock()
    # fetchrow lève UniqueViolationError (= workspace déjà existant)
    conn_in_tx.fetchrow = AsyncMock(
        side_effect=asyncpg.UniqueViolationError("duplicate key value violates unique constraint")
    )
    conn_in_tx.execute = AsyncMock(return_value=None)

    with (
        patch("rag.services.workspaces.get_dimension_or_raise", new=AsyncMock(return_value=1024)),
        patch("rag.services.workspaces.transaction") as mock_tx,
        pytest.raises(WorkspaceAlreadyExists),
    ):
        mock_tx.return_value.__aenter__ = AsyncMock(return_value=conn_in_tx)
        mock_tx.return_value.__aexit__ = AsyncMock(return_value=False)

        await create_workspace(
            request=_make_request(name="existing-ws", vault="rag"),
            config_pool=pool,
            admin_dsn="postgresql://stub",
            resolver=resolver,
            harpocrate_vaults_service=harpo,
        )

    # delete_secret doit avoir été appelé pour rollback le secret écrit
    harpo.delete_secret.assert_called_once()
    call_kwargs = harpo.delete_secret.call_args.kwargs
    assert call_kwargs["vault_name"] == "rag"
    assert call_kwargs["path"] == "wsapi_existing-ws"
