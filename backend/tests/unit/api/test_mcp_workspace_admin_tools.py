from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api.errors import ChunkingChangeRequiresReindex, IndexerChangeRequiresReindex
from rag.api.mcp_standard import _KeyCtx, _ws_ctx
from rag.api.mcp_workspace_admin_tools import (
    WORKSPACE_ADMIN_REFUSAL,
    register_workspace_admin_tools,
)
from rag.schemas.vault_endpoints import EndpointIndexerSpec, EndpointOut
from rag.services import vault_endpoints as endpoints_svc


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self) -> Any:
        def deco(fn: Any) -> Any:
            self.tools[fn.__name__] = fn
            return fn

        return deco


class _FakePool:
    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self.fetchval = AsyncMock(return_value=None)
        self.fetchrow = AsyncMock(return_value=None)
        self.execute = AsyncMock(return_value="UPDATE 1")

    def acquire(self) -> Any:
        conn = self._conn

        class _CM:
            async def __aenter__(self) -> Any:
                return conn

            async def __aexit__(self, *args: Any) -> bool:
                return False

        return _CM()


_OWNER = "b" * 64


def _make_ctx(conn: Any, *, scope: str = "admin") -> _KeyCtx:
    return _KeyCtx(
        owner_id=_OWNER,
        scope=scope,
        config_pool=_FakePool(conn),
        pool_registry=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        default_vault_name="rag",
        admin_dsn="postgresql://admin@db/postgres",
        vaults_service=MagicMock(),
    )


def _endpoint_out() -> EndpointOut:
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


def _register(conn: Any, *, scope: str = "admin") -> tuple[dict[str, Any], _KeyCtx]:
    mcp = FakeMCP()
    register_workspace_admin_tools(mcp, _ws_ctx)
    ctx = _make_ctx(conn, scope=scope)
    _ws_ctx.set(ctx)
    return mcp.tools, ctx


@pytest.mark.asyncio
async def test_all_tools_require_admin() -> None:
    tools, _ = _register(MagicMock(), scope="read_write")
    assert await tools["create_workspace"]("ws", "coffre", "ep") == WORKSPACE_ADMIN_REFUSAL
    assert await tools["reset_workspace_from_endpoint"]("ws") == WORKSPACE_ADMIN_REFUSAL
    assert await tools["set_default_chunking_strategy"]("ws") == WORKSPACE_ADMIN_REFUSAL


@pytest.mark.asyncio
async def test_create_workspace_unknown_vault() -> None:
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    tools, _ = _register(conn)

    out = await tools["create_workspace"]("mon-ws", "inconnu", "azure-prod")

    assert "Coffre 'inconnu' introuvable" in out


@pytest.mark.asyncio
async def test_create_workspace_invalid_name(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4(), "owner_id": _OWNER})
    monkeypatch.setattr(
        endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint_out()])
    )
    tools, _ = _register(conn)

    out = await tools["create_workspace"]("Nom Invalide!", "coffre-a", "azure-prod")

    assert "Paramètres invalides" in out


@pytest.mark.asyncio
async def test_create_workspace_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.events.emit as emit_mod
    import rag.services.workspaces as ws_svc

    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4(), "owner_id": _OWNER})
    monkeypatch.setattr(
        endpoints_svc, "list_endpoints", AsyncMock(return_value=[_endpoint_out()])
    )
    create_mock = AsyncMock(return_value={"name": "mon-ws", "label": "Mon WS"})
    monkeypatch.setattr(ws_svc, "create_workspace", create_mock)
    emit_mock = AsyncMock()
    monkeypatch.setattr(emit_mod, "emit_workflow_event", emit_mock)
    tools, _ctx = _register(conn)

    out = await tools["create_workspace"]("mon-ws", "coffre-a", "azure-prod", label="Mon WS")

    assert json.loads(out)["name"] == "mon-ws"
    resolved = create_mock.call_args.kwargs["request"]
    assert resolved.owner_id == _OWNER
    assert resolved.indexer.provider == "openai"
    emit_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_requires_confirm_on_model_change(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.services.endpoint_refresh as refresh_mod
    import rag.services.workspaces as ws_svc

    monkeypatch.setattr(
        ws_svc, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4())
    )
    monkeypatch.setattr(
        refresh_mod,
        "refresh_workspace_from_endpoint",
        AsyncMock(
            side_effect=IndexerChangeRequiresReindex(
                workspace="mon-ws",
                current="openai/small",
                requested="voyage/large",
                documents_count=42,
            )
        ),
    )
    tools, _ = _register(MagicMock())

    out = await tools["reset_workspace_from_endpoint"]("mon-ws")

    assert "42 documents" in out
    assert "confirm=true" in out


@pytest.mark.asyncio
async def test_reset_unknown_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.services.workspaces as ws_svc

    monkeypatch.setattr(ws_svc, "resolve_owned_workspace_id", AsyncMock(return_value=None))
    tools, _ = _register(MagicMock())

    out = await tools["reset_workspace_from_endpoint"]("fantome")

    assert "introuvable" in out


@pytest.mark.asyncio
async def test_set_default_strategy_requires_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.services.jobs as jobs_mod
    import rag.services.workspaces as ws_svc

    monkeypatch.setattr(
        ws_svc, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4())
    )
    monkeypatch.setattr(
        jobs_mod,
        "apply_default_strategy_change",
        AsyncMock(
            side_effect=ChunkingChangeRequiresReindex(
                workspace="mon-ws", current="default_strategy_id=None", new="x"
            )
        ),
    )
    tools, ctx = _register(MagicMock())
    ctx.config_pool.fetchval = AsyncMock(return_value=7)

    out = await tools["set_default_chunking_strategy"]("mon-ws", str(uuid4()))

    assert "7 documents" in out
    assert "confirm=true" in out


@pytest.mark.asyncio
async def test_set_default_strategy_no_change(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.services.jobs as jobs_mod
    import rag.services.workspaces as ws_svc

    monkeypatch.setattr(
        ws_svc, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4())
    )
    monkeypatch.setattr(
        jobs_mod, "apply_default_strategy_change", AsyncMock(return_value="no_change")
    )
    tools, _ = _register(MagicMock())

    out = await tools["set_default_chunking_strategy"]("mon-ws", str(uuid4()))

    assert "Aucun changement" in out


@pytest.mark.asyncio
async def test_set_default_strategy_updated(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.services.jobs as jobs_mod
    import rag.services.workspaces as ws_svc

    sid = uuid4()
    monkeypatch.setattr(
        ws_svc, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4())
    )
    monkeypatch.setattr(
        jobs_mod,
        "apply_default_strategy_change",
        AsyncMock(return_value=("updated", {"default_strategy_id": str(sid)})),
    )
    tools, _ = _register(MagicMock())

    payload = json.loads(await tools["set_default_chunking_strategy"]("mon-ws", str(sid)))

    assert payload["status"] == "updated"
    assert payload["default_strategy_id"] == str(sid)


@pytest.mark.asyncio
async def test_set_default_strategy_invalid_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.services.workspaces as ws_svc

    monkeypatch.setattr(
        ws_svc, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4())
    )
    tools, _ = _register(MagicMock())

    out = await tools["set_default_chunking_strategy"]("mon-ws", "pas-un-uuid")

    assert "identifiant invalide" in out
