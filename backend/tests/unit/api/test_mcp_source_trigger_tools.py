from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.mcp_source_tools import SOURCE_ADMIN_REFUSAL, register_source_tools
from rag.api.mcp_standard import _KeyCtx, _ws_ctx
from rag.api.mcp_trigger_tools import TRIGGER_ADMIN_REFUSAL, register_trigger_tools
from rag.schemas.enrichments import TriggerOut
from rag.services import sources as sources_svc
from rag.services import triggers as triggers_svc
from rag.services import workspaces as workspaces_svc


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
        self.fetch = AsyncMock(return_value=[])
        self.fetchval = AsyncMock(return_value=None)

    def acquire(self) -> Any:
        conn = self._conn

        class _CM:
            async def __aenter__(self) -> Any:
                return conn

            async def __aexit__(self, *args: Any) -> bool:
                return False

        return _CM()


_OWNER = "c" * 64


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


def _register(conn: Any, *, scope: str = "admin") -> tuple[dict[str, Any], _KeyCtx]:
    mcp = FakeMCP()
    register_source_tools(mcp, _ws_ctx)
    register_trigger_tools(mcp, _ws_ctx)
    ctx = _make_ctx(conn, scope=scope)
    _ws_ctx.set(ctx)
    return mcp.tools, ctx


@pytest.fixture(autouse=True)
def _owned_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workspaces_svc, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4())
    )


# ── Sources git ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_git_source_requires_admin() -> None:
    tools, _ = _register(MagicMock(), scope="read_write")
    out = await tools["add_git_source"]("ws", "src", "https://github.com/o/r.git")
    assert out == SOURCE_ADMIN_REFUSAL


@pytest.mark.asyncio
async def test_add_git_source_builds_config(monkeypatch: pytest.MonkeyPatch) -> None:
    add_mock = AsyncMock(return_value={"id": str(uuid4()), "name": "docs"})
    monkeypatch.setattr(sources_svc, "add_source", add_mock)
    tools, _ = _register(MagicMock())

    out = await tools["add_git_source"](
        "mon-ws",
        "docs",
        "https://github.com/o/r.git",
        branch="main",
        include=["**/*.md"],
        exclude=["**/node_modules/**"],
        sync_interval_seconds=3600,
        auth_type="token",
        auth_ref="github_token",
    )

    req = add_mock.call_args.kwargs["request"]
    assert req.config["url"] == "https://github.com/o/r.git"
    assert req.config["branch"] == "main"
    assert req.config["include"] == ["**/*.md"]
    assert req.config["sync_interval_seconds"] == 3600
    assert req.auth_ref == "github_token"
    assert add_mock.call_args.kwargs["owner_id"] == _OWNER
    assert json.loads(out)["name"] == "docs"


@pytest.mark.asyncio
async def test_add_git_source_invalid_name() -> None:
    tools, _ = _register(MagicMock())
    out = await tools["add_git_source"]("mon-ws", "Nom Invalide", "https://x/r.git")
    assert "Paramètres invalides" in out


@pytest.mark.asyncio
async def test_add_git_source_inaccessible_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sources_svc,
        "add_source",
        AsyncMock(side_effect=HTTPException(403, "credential not accessible")),
    )
    tools, _ = _register(MagicMock())

    out = await tools["add_git_source"](
        "mon-ws", "docs", "https://x/r.git", auth_ref="privee"
    )

    assert "Refusé" in out


@pytest.mark.asyncio
async def test_list_git_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sources_svc,
        "list_sources",
        AsyncMock(return_value=[{"id": str(uuid4()), "name": "docs", "type": "git"}]),
    )
    tools, _ = _register(MagicMock())

    payload = json.loads(await tools["list_git_sources"]("mon-ws"))

    assert payload[0]["name"] == "docs"


# ── Triggers de chunking ─────────────────────────────────────────────────────


def _trigger_out(pattern: str = "backlog/**/*.md") -> TriggerOut:
    return TriggerOut(
        id=uuid4(),
        pattern=pattern,
        enabled=True,
        strategy_id=uuid4(),
        created_at=datetime(2026, 1, 1),
    )


@pytest.mark.asyncio
async def test_create_trigger_requires_admin() -> None:
    tools, _ = _register(MagicMock(), scope="read")
    out = await tools["create_chunking_trigger"]("ws", "**/*.md")
    assert out == TRIGGER_ADMIN_REFUSAL


@pytest.mark.asyncio
async def test_create_trigger_counts_matching_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trigger = _trigger_out()
    monkeypatch.setattr(triggers_svc, "create_trigger", AsyncMock(return_value=trigger))
    tools, ctx = _register(MagicMock())
    ctx.config_pool.fetch = AsyncMock(
        return_value=[
            {"path": "backlog/2026/tache.md"},
            {"path": "docs/guide.md"},
            {"path": "backlog/note.md"},
        ]
    )

    payload = json.loads(
        await tools["create_chunking_trigger"](
            "mon-ws", "backlog/**/*.md", strategy_id=str(uuid4())
        )
    )

    assert payload["matching_indexed_documents"] == 2
    assert "réindexation" in payload["note"]


@pytest.mark.asyncio
async def test_create_trigger_invalid_pattern() -> None:
    tools, _ = _register(MagicMock())
    out = await tools["create_chunking_trigger"]("mon-ws", "/absolu/*.md")
    assert "Paramètres invalides" in out


@pytest.mark.asyncio
async def test_update_trigger_exclusive_params() -> None:
    tools, _ = _register(MagicMock())
    out = await tools["update_chunking_trigger"](
        "mon-ws", str(uuid4()), strategy_id=str(uuid4()), clear_strategy=True
    )
    assert "exclusifs" in out


@pytest.mark.asyncio
async def test_update_trigger_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triggers_svc, "patch_trigger", AsyncMock(return_value=None))
    tools, _ = _register(MagicMock())

    out = await tools["update_chunking_trigger"]("mon-ws", str(uuid4()), enabled=False)

    assert "introuvable" in out


@pytest.mark.asyncio
async def test_delete_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(triggers_svc, "delete_trigger", AsyncMock(return_value=True))
    tools, _ = _register(MagicMock())

    out = await tools["delete_chunking_trigger"]("mon-ws", str(uuid4()))

    assert "supprimé" in out


@pytest.mark.asyncio
async def test_list_triggers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        triggers_svc, "list_triggers", AsyncMock(return_value=[_trigger_out()])
    )
    tools, _ = _register(MagicMock())

    payload = json.loads(await tools["list_chunking_triggers"]("mon-ws"))

    assert payload[0]["pattern"] == "backlog/**/*.md"
