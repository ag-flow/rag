from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api import mcp_ops_tools as mod
from rag.api.mcp_ops_tools import register_ops_tools
from rag.api.mcp_standard import _KeyCtx, _ws_ctx


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

    def acquire(self) -> Any:
        conn = self._conn

        class _CM:
            async def __aenter__(self) -> Any:
                return conn

            async def __aexit__(self, *args: Any) -> bool:
                return False

        return _CM()


def _make_ctx(*, owner_id: str = "owner-1") -> _KeyCtx:
    return _KeyCtx(
        owner_id=owner_id,
        scope="read",
        config_pool=_FakePool(MagicMock()),
        pool_registry=MagicMock(),
        resolver=MagicMock(),
        client_provider=MagicMock(),
        default_vault_name=None,
    )


@pytest.fixture
def tools() -> dict[str, Any]:
    mcp = FakeMCP()
    register_ops_tools(mcp, _ws_ctx)
    return mcp.tools


async def _call(tool: Any, ctx: _KeyCtx, /, **kwargs: Any) -> str:
    token = _ws_ctx.set(ctx)
    try:
        return await tool(**kwargs)
    finally:
        _ws_ctx.reset(token)


class TestOwnerScoping:
    @pytest.mark.asyncio
    async def test_unknown_workspace_returns_message(self, tools, monkeypatch):
        # resolve_owned_workspace_id → None : workspace d'autrui / inconnu.
        monkeypatch.setattr(mod, "resolve_owned_workspace_id", AsyncMock(return_value=None))
        list_jobs = AsyncMock()
        monkeypatch.setattr(mod, "list_jobs", list_jobs)
        result = await _call(tools["list_index_jobs"], _make_ctx(), workspace="ghost")
        assert "introuvable" in result.lower()
        list_jobs.assert_not_awaited()  # jamais appelé si non visible

    @pytest.mark.asyncio
    async def test_resolve_uses_ctx_owner_id(self, tools, monkeypatch):
        resolve = AsyncMock(return_value=uuid4())
        monkeypatch.setattr(mod, "resolve_owned_workspace_id", resolve)
        monkeypatch.setattr(mod, "list_jobs", AsyncMock(return_value=[]))
        await _call(tools["list_index_jobs"], _make_ctx(owner_id="owner-42"), workspace="ws")
        assert resolve.await_args.kwargs["owner_id"] == "owner-42"


class TestListIndexJobs:
    @pytest.mark.asyncio
    async def test_lists_and_limits(self, tools, monkeypatch):
        monkeypatch.setattr(mod, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4()))
        jobs = [{"id": str(i), "status": "done"} for i in range(5)]
        monkeypatch.setattr(mod, "list_jobs", AsyncMock(return_value=jobs))
        result = await _call(tools["list_index_jobs"], _make_ctx(), workspace="ws", limit=2)
        assert '"0"' in result and '"1"' in result
        assert '"2"' not in result  # tronqué à limit=2


class TestGetIndexJob:
    @pytest.mark.asyncio
    async def test_returns_job_and_files(self, tools, monkeypatch):
        monkeypatch.setattr(mod, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4()))
        monkeypatch.setattr(
            mod, "get_job", AsyncMock(return_value={"id": "j1", "status": "done"})
        )
        monkeypatch.setattr(
            mod,
            "list_job_files",
            AsyncMock(
                return_value={"files": [{"path": "a.md", "change_type": "added"}], "total": 1}
            ),
        )
        result = await _call(tools["get_index_job"], _make_ctx(), workspace="ws", job_id="j1")
        assert "a.md" in result
        assert '"files_total": 1' in result

    @pytest.mark.asyncio
    async def test_job_not_found_returns_message(self, tools, monkeypatch):
        from rag.services.jobs import JobNotFound

        monkeypatch.setattr(mod, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4()))
        monkeypatch.setattr(mod, "get_job", AsyncMock(side_effect=JobNotFound("j9")))
        result = await _call(tools["get_index_job"], _make_ctx(), workspace="ws", job_id="j9")
        assert "j9" in result
        assert "introuvable" in result.lower()


class TestChunkingConfig:
    @pytest.mark.asyncio
    async def test_returns_config(self, tools, monkeypatch):
        monkeypatch.setattr(mod, "resolve_owned_workspace_id", AsyncMock(return_value=uuid4()))
        monkeypatch.setattr(
            mod,
            "get_chunking_config",
            AsyncMock(return_value={"strategy": "prose", "engine": "structured"}),
        )
        result = await _call(tools["get_chunking_configuration"], _make_ctx(), workspace="ws")
        assert "prose" in result
        assert "structured" in result
