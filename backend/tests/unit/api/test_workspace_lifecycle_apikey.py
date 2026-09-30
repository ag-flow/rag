"""POST / DELETE /api/v1/workspaces par clé API (ticket 21b879b5) : scope
read_write+, endpoint par coffre + slug, suppression limitée aux workspaces
possédés et confirmée, présence dans le contrat OpenAPI « clé API »."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.contracts import build_contracts_router
from rag.api.errors import WorkspaceNotFound, register_error_handlers
from rag.api.workspace_lifecycle import build_workspace_lifecycle_router
from rag.auth.workspace_auth import OwnerAuthContext, require_apikey_owner
from rag.schemas.vault_endpoints import EndpointIndexerSpec, EndpointOut
from rag.services import workspace_lifecycle as lifecycle
from rag.services import workspaces as workspaces_svc

_OWNER = "a" * 64
_CREATED = {
    "id": str(uuid4()),
    "name": "mon-ws",
    "label": "Mon WS",
    "description": "",
    "created_at": "2026-09-30T10:00:00+00:00",
}


def _endpoint() -> EndpointOut:
    return EndpointOut(
        id=uuid4(),
        vault_id=uuid4(),
        label="Azure Prod",
        slug="azure-prod",
        indexer=EndpointIndexerSpec(provider="openai", model="text-embedding-3-small"),
        rerank=None,
        llm=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


def _client(scope: str = "read_write") -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=MagicMock())
    acquire.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire)
    app.state.pools = SimpleNamespace(config_pool=pool)
    app.state.admin_dsn = "postgresql://admin@db/postgres"
    app.state.resolver = MagicMock()
    app.state.harpocrate_vaults_service = MagicMock()
    app.include_router(build_workspace_lifecycle_router(), prefix="/api/v1")
    app.include_router(build_contracts_router())
    app.dependency_overrides[require_apikey_owner] = lambda: OwnerAuthContext(
        owner_id=_OWNER, scope=scope
    )
    return TestClient(app)


@pytest.fixture
def svc(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    mocks = SimpleNamespace(
        find_endpoint=AsyncMock(return_value=_endpoint()),
        create=AsyncMock(return_value=_CREATED),
        emit=AsyncMock(),
        owned=AsyncMock(return_value=uuid4()),
        delete=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "resolve_endpoint_by_slug", mocks.find_endpoint)
    monkeypatch.setattr(lifecycle, "emit_workspace_created", mocks.emit)
    monkeypatch.setattr(lifecycle, "resolve_owned_workspace_for_deletion", mocks.owned)
    monkeypatch.setattr(workspaces_svc, "create_workspace", mocks.create)
    monkeypatch.setattr(workspaces_svc, "delete_workspace", mocks.delete)
    return mocks


_CREATE_BODY: dict[str, Any] = {"name": "mon-ws", "vault": "coffre-a", "endpoint": "azure-prod"}


class TestCreate:
    def test_create_with_write_key_returns_201_owned_by_key(self, svc: SimpleNamespace) -> None:
        resp = _client().post("/api/v1/workspaces", json=_CREATE_BODY)
        assert resp.status_code == 201
        assert resp.json()["name"] == "mon-ws"
        resolved = svc.create.await_args.kwargs["request"]
        assert resolved.owner_id == _OWNER
        assert resolved.label == "mon-ws"  # label par défaut = name
        svc.find_endpoint.assert_awaited_once()
        assert svc.find_endpoint.await_args.kwargs == {
            "owner_id": _OWNER,
            "vault": "coffre-a",
            "endpoint": "azure-prod",
        }
        svc.emit.assert_awaited_once()

    def test_create_with_admin_key_is_allowed(self, svc: SimpleNamespace) -> None:
        assert _client("admin").post("/api/v1/workspaces", json=_CREATE_BODY).status_code == 201

    def test_create_with_read_key_is_refused_401(self, svc: SimpleNamespace) -> None:
        resp = _client("read").post("/api/v1/workspaces", json=_CREATE_BODY)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "insufficient_scope"
        svc.create.assert_not_awaited()

    def test_create_unknown_vault_returns_404(self, svc: SimpleNamespace) -> None:
        svc.find_endpoint.side_effect = lifecycle.VaultNotVisible("coffre-a")
        resp = _client().post("/api/v1/workspaces", json=_CREATE_BODY)
        assert resp.status_code == 404
        assert resp.json()["error"] == "vault_not_found"
        svc.create.assert_not_awaited()

    def test_create_unknown_endpoint_returns_404(self, svc: SimpleNamespace) -> None:
        svc.find_endpoint.side_effect = lifecycle.EndpointNotInVault("coffre-a", "x")
        resp = _client().post("/api/v1/workspaces", json=_CREATE_BODY)
        assert resp.status_code == 404
        assert resp.json()["error"] == "endpoint_not_found"

    @pytest.mark.parametrize(
        "body",
        [
            {**_CREATE_BODY, "name": "Nom Invalide!"},
            {**_CREATE_BODY, "name": "../etc"},
            {**_CREATE_BODY, "inconnu": 1},
            {"name": "mon-ws", "vault": "coffre-a"},
        ],
    )
    def test_create_invalid_body_returns_422(
        self, svc: SimpleNamespace, body: dict[str, Any]
    ) -> None:
        assert _client().post("/api/v1/workspaces", json=body).status_code == 422
        svc.create.assert_not_awaited()


class TestDelete:
    def _delete(self, client: TestClient, body: dict[str, Any]) -> Any:
        return client.request("DELETE", "/api/v1/workspaces", json=body)

    def test_delete_owned_with_confirm_returns_204(self, svc: SimpleNamespace) -> None:
        resp = self._delete(_client(), {"workspace": "mon-ws", "confirm": True})
        assert resp.status_code == 204
        assert svc.owned.await_args.kwargs == {"owner_id": _OWNER, "workspace": "mon-ws"}
        assert svc.delete.await_args.kwargs["name"] == "mon-ws"

    @pytest.mark.parametrize(
        "body",
        [
            {"workspace": "mon-ws"},
            {"workspace": "mon-ws", "confirm": False},
            {"workspace": "mon-ws", "confirm": "true"},
        ],
    )
    def test_delete_without_explicit_confirm_returns_422(
        self, svc: SimpleNamespace, body: dict[str, Any]
    ) -> None:
        assert self._delete(_client(), body).status_code == 422
        svc.delete.assert_not_awaited()

    def test_delete_not_owned_or_shared_returns_404(self, svc: SimpleNamespace) -> None:
        svc.owned.side_effect = WorkspaceNotFound("autre-ws")
        resp = self._delete(_client(), {"workspace": "autre-ws", "confirm": True})
        assert resp.status_code == 404
        assert resp.json()["error"] == "workspace_not_found"
        svc.delete.assert_not_awaited()

    def test_delete_with_read_key_is_refused_401(self, svc: SimpleNamespace) -> None:
        resp = self._delete(_client("read"), {"workspace": "mon-ws", "confirm": True})
        assert resp.status_code == 401
        svc.owned.assert_not_awaited()
        svc.delete.assert_not_awaited()


def test_both_operations_are_in_the_apikey_contract() -> None:
    spec = _client().get("/api/contracts/openapi-apikey").json()
    ops = spec["paths"]["/api/v1/workspaces"]
    assert set(ops) == {"post", "delete"}
    assert ops["post"]["summary"] == "Créer un workspace"
    assert {"401", "404", "409", "422"} <= set(ops["post"]["responses"])
    assert ops["delete"]["requestBody"]["required"] is True
