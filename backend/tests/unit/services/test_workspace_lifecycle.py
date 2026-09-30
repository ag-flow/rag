"""Service partagé du cycle de vie : endpoint par coffre + slug, workspace
possédé pour la suppression (jamais un partagé ni celui d'autrui)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api.errors import WorkspaceNotFound
from rag.schemas.vault_endpoints import EndpointIndexerSpec, EndpointOut
from rag.services import vault_endpoints as endpoints_svc
from rag.services import workspace_lifecycle as lifecycle

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


@pytest.mark.asyncio
async def test_resolve_endpoint_by_slug_returns_matching_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = MagicMock(fetchrow=AsyncMock(return_value={"id": uuid4()}))
    monkeypatch.setattr(
        endpoints_svc,
        "list_endpoints",
        AsyncMock(return_value=[_endpoint("a"), _endpoint("azure-prod")]),
    )
    ep = await lifecycle.resolve_endpoint_by_slug(
        conn, owner_id=_OWNER, vault="coffre", endpoint="azure-prod"
    )
    assert ep.slug == "azure-prod"
    assert conn.fetchrow.await_args.args[1:] == (_OWNER, "coffre")


@pytest.mark.asyncio
async def test_resolve_endpoint_by_slug_unknown_vault_raises() -> None:
    conn = MagicMock(fetchrow=AsyncMock(return_value=None))
    with pytest.raises(lifecycle.VaultNotVisible):
        await lifecycle.resolve_endpoint_by_slug(
            conn, owner_id=_OWNER, vault="coffre", endpoint="x"
        )


@pytest.mark.asyncio
async def test_resolve_endpoint_by_slug_unknown_endpoint_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = MagicMock(fetchrow=AsyncMock(return_value={"id": uuid4()}))
    monkeypatch.setattr(endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint("a")]))
    with pytest.raises(lifecycle.EndpointNotInVault):
        await lifecycle.resolve_endpoint_by_slug(
            conn, owner_id=_OWNER, vault="coffre", endpoint="absent"
        )


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
