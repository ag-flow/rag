from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.schemas.mcp import SearchHit
from rag.services.mcp import McpWorkspaceRef, search


class TestLoadHybridConfig:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(self):
        from rag.services.mcp import _load_hybrid_config

        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        result = await _load_hybrid_config(pool, uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_row_exists(self):
        from rag.services.mcp import _load_hybrid_config

        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            return_value={"enabled": True, "rrf_k": 60, "fts_config": "simple"}
        )
        result = await _load_hybrid_config(pool, uuid4())
        assert result == {"enabled": True, "rrf_k": 60, "fts_config": "simple"}


def _build_config_pool(ws_id: object, api_key: str, name: str) -> MagicMock:
    """Pool config qui répond à _authenticate puis _load_workspace_context."""
    auth_row = {
        "id": ws_id,
        "api_key_ref": f"${{vault://rag:{name}_apikey}}",
        "indexer_used": "openai/text-embedding-3-small",
    }
    ctx_row: dict[str, Any] = {
        "workspace_name": name,
        "rag_cnx": "dsn",
        "provider": "openai",
        "model": "text-embedding-3-small",
        "api_key_ref": None,
        "base_url": None,
        "service": "openai",
        "rerank_provider": None,
        "rerank_model": None,
        "rerank_api_key_ref": None,
        "rerank_base_url": None,
        "rerank_top_k_pre_rerank": None,
    }
    call_count = 0

    async def _fetchrow(_query: str, *args: Any) -> dict[str, Any] | None:
        nonlocal call_count
        call_count += 1
        return auth_row if call_count == 1 else ctx_row

    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=_fetchrow)
    pool.fetchval = AsyncMock(return_value=None)
    return pool


def _fake_hit(name: str) -> SearchHit:
    return SearchHit(
        workspace=name, indexer="openai/m", path="a.py", chunk_index=0, content="x", score=0.9
    )


class TestSearchOneHybridDispatch:
    @pytest.mark.asyncio
    async def test_uses_vector_search_when_no_hybrid_config(self, monkeypatch):
        from rag.auth.workspace_auth import ApiKeyCache
        from rag.services import mcp

        ws_id = uuid4()
        pool = _build_config_pool(ws_id, "k", "ws")
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=MagicMock())

        fake_vector = AsyncMock(return_value=[_fake_hit("ws")])
        fake_hybrid = AsyncMock(return_value=[])
        monkeypatch.setattr(mcp, "vector_search", fake_vector)
        monkeypatch.setattr(mcp, "hybrid_search", fake_hybrid)
        monkeypatch.setattr(mcp, "_load_hybrid_config", AsyncMock(return_value=None))

        provider = MagicMock()
        provider.embed_query = AsyncMock(return_value=[0.1])

        await search(
            refs=[McpWorkspaceRef(name="ws", api_key="k")],
            query="x",
            top_k=5,
            min_score=0.3,
            config_pool=pool,
            pool_registry=registry,
            apikey_cache=ApiKeyCache(),
            secret_resolver=MagicMock(**{"resolve_with_retry": AsyncMock(return_value="k")}),
            provider_factory=lambda **_: provider,
        )
        fake_vector.assert_awaited_once()
        fake_hybrid.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_hybrid_search_when_enabled(self, monkeypatch):
        from rag.auth.workspace_auth import ApiKeyCache
        from rag.services import mcp

        ws_id = uuid4()
        pool = _build_config_pool(ws_id, "k", "ws")
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=MagicMock())

        fake_vector = AsyncMock(return_value=[])
        fake_hybrid = AsyncMock(return_value=[_fake_hit("ws")])
        monkeypatch.setattr(mcp, "vector_search", fake_vector)
        monkeypatch.setattr(mcp, "hybrid_search", fake_hybrid)
        monkeypatch.setattr(
            mcp,
            "_load_hybrid_config",
            AsyncMock(return_value={"enabled": True, "rrf_k": 60, "fts_config": "simple"}),
        )

        provider = MagicMock()
        provider.embed_query = AsyncMock(return_value=[0.1])

        await search(
            refs=[McpWorkspaceRef(name="ws", api_key="k")],
            query="x",
            top_k=5,
            min_score=0.3,
            config_pool=pool,
            pool_registry=registry,
            apikey_cache=ApiKeyCache(),
            secret_resolver=MagicMock(**{"resolve_with_retry": AsyncMock(return_value="k")}),
            provider_factory=lambda **_: provider,
        )
        fake_hybrid.assert_awaited_once()
        fake_vector.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_vector_search_when_hybrid_disabled(self, monkeypatch):
        from rag.auth.workspace_auth import ApiKeyCache
        from rag.services import mcp

        ws_id = uuid4()
        pool = _build_config_pool(ws_id, "k", "ws")
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=MagicMock())

        fake_vector = AsyncMock(return_value=[])
        fake_hybrid = AsyncMock(return_value=[])
        monkeypatch.setattr(mcp, "vector_search", fake_vector)
        monkeypatch.setattr(mcp, "hybrid_search", fake_hybrid)
        monkeypatch.setattr(
            mcp,
            "_load_hybrid_config",
            AsyncMock(
                return_value={"enabled": False, "rrf_k": 60, "fts_config": "simple"}
            ),
        )

        provider = MagicMock()
        provider.embed_query = AsyncMock(return_value=[0.1])

        await search(
            refs=[McpWorkspaceRef(name="ws", api_key="k")],
            query="x",
            top_k=5,
            min_score=0.3,
            config_pool=pool,
            pool_registry=registry,
            apikey_cache=ApiKeyCache(),
            secret_resolver=MagicMock(**{"resolve_with_retry": AsyncMock(return_value="k")}),
            provider_factory=lambda **_: provider,
        )
        fake_vector.assert_awaited_once()
        fake_hybrid.assert_not_awaited()
