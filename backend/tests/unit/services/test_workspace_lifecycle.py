"""Service partagé du cycle de vie : endpoint par coffre + slug, workspace
possédé pour la suppression (jamais un partagé ni celui d'autrui)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api.errors import WorkspaceNotFound
from rag.schemas.vault_endpoints import EndpointIndexerSpec, EndpointOut
from rag.services import endpoint_sharing as sharing_svc
from rag.services import vault_endpoints as endpoints_svc
from rag.services import workspace_lifecycle as lifecycle
from rag.services.endpoint_sharing import UsableEndpoint

_OWNER = "b" * 64


def _endpoint(slug: str) -> EndpointOut:
    return EndpointOut(
        id=uuid4(),
        vault_id=uuid4(),
        label=slug,
        slug=slug,
        indexer=EndpointIndexerSpec(provider="openai", model="text-embedding-3-small"),
        rerank=None,
        llm=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _usable(ep: EndpointOut, access: str) -> UsableEndpoint:
    return UsableEndpoint(
        id=ep.id,
        slug=ep.slug,
        label=ep.label,
        vault_id=ep.vault_id,
        vault_name="coffre",
        vault_label="Coffre",
        access=access,  # type: ignore[arg-type]
        indexer=("openai", "text-embedding-3-small"),
        rerank=None,
        llm=None,
    )


@pytest.mark.parametrize("access", ["owned", "default", "shared"])
@pytest.mark.asyncio
async def test_resolve_endpoint_by_slug_returns_usable_endpoint(
    monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    """Coffre visible OU endpoint partagé : la règle unique tranche, puis la
    config complète est relue pour le snapshot."""
    ep = _endpoint("azure-prod")
    find = AsyncMock(return_value=_usable(ep, access))
    monkeypatch.setattr(sharing_svc, "db_find_usable_endpoint_by_slug", find)
    monkeypatch.setattr(endpoints_svc, "get_endpoint", AsyncMock(return_value=ep))

    got = await lifecycle.resolve_endpoint_by_slug(
        MagicMock(), owner_id=_OWNER, vault="coffre", endpoint="azure-prod"
    )

    assert got is ep
    assert find.await_args.kwargs == {
        "owner_id": _OWNER,
        "vault": "coffre",
        "endpoint": "azure-prod",
    }


@pytest.mark.asyncio
async def test_resolve_endpoint_by_slug_unknown_vault_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sharing_svc, "db_find_usable_endpoint_by_slug", AsyncMock(return_value=None)
    )
    conn = MagicMock(fetchrow=AsyncMock(return_value=None))
    with pytest.raises(lifecycle.VaultNotVisible):
        await lifecycle.resolve_endpoint_by_slug(
            conn, owner_id=_OWNER, vault="coffre", endpoint="x"
        )


@pytest.mark.asyncio
async def test_resolve_endpoint_by_slug_unknown_endpoint_in_visible_vault_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sharing_svc, "db_find_usable_endpoint_by_slug", AsyncMock(return_value=None)
    )
    conn = MagicMock(fetchrow=AsyncMock(return_value={"id": uuid4()}))
    with pytest.raises(lifecycle.EndpointNotInVault):
        await lifecycle.resolve_endpoint_by_slug(
            conn, owner_id=_OWNER, vault="coffre", endpoint="absent"
        )
    assert conn.fetchrow.await_args.args[1:] == (_OWNER, "coffre")


@pytest.mark.asyncio
async def test_owned_workspace_for_deletion_returns_id() -> None:
    ws_id = uuid4()
    conn = MagicMock(fetchrow=AsyncMock(return_value={"id": ws_id}))
    got = await lifecycle.resolve_owned_workspace_for_deletion(
        conn, owner_id=_OWNER, workspace="mon-ws"
    )
    assert got == ws_id


@pytest.mark.asyncio
async def test_owned_workspace_for_deletion_not_found_raises_404() -> None:
    conn = MagicMock(fetchrow=AsyncMock(return_value=None))
    with pytest.raises(WorkspaceNotFound):
        await lifecycle.resolve_owned_workspace_for_deletion(
            conn, owner_id=_OWNER, workspace="partage"
        )


def test_owned_workspace_query_excludes_shared_workspaces() -> None:
    # Un workspace partagé (owner_id NULL) ne doit JAMAIS être supprimable par une
    # clé : la requête exige l'égalité stricte, sans « OR owner_id IS NULL ».
    sql = lifecycle._OWNED_WS_SQL
    assert "owner_id = $2" in sql
    assert "IS NULL" not in sql
