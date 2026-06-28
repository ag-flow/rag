from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.api.mcp_standard import _WsCtx


class TestWsCtxExtended:
    def test_ws_ctx_has_workspace_id_and_config_pool(self):
        ws_id = uuid4()
        pool = MagicMock()
        ctx = _WsCtx(
            workspace_name="ws",
            rag_cnx="dsn",
            indexer_service="openai",
            indexer_provider="openai",
            indexer_model="text-embedding-3-small",
            indexer_api_key_ref=None,
            indexer_base_url=None,
            pool_registry=MagicMock(),
            resolver=MagicMock(),
            workspace_id=ws_id,
            config_pool=pool,
        )
        assert ctx.workspace_id == ws_id
        assert ctx.config_pool is pool


class TestRagSearchEnrichmentParams:
    @pytest.mark.asyncio
    async def test_rag_search_accepts_scope_param(self, monkeypatch):
        from rag.api import mcp_standard as mod
        from rag.api.mcp_standard import _ws_ctx

        ws_id = uuid4()
        pool = MagicMock()
        pool_registry = MagicMock()
        pool_registry.get_workspace_pool = AsyncMock(return_value=MagicMock())
        ctx = _WsCtx(
            workspace_name="ws", rag_cnx="dsn", indexer_service="openai",
            indexer_provider="openai", indexer_model="m",
            indexer_api_key_ref=None, indexer_base_url=None,
            pool_registry=pool_registry, resolver=MagicMock(),
            workspace_id=ws_id, config_pool=pool,
        )
        token = _ws_ctx.set(ctx)
        try:
            fake_provider = MagicMock()
            fake_provider.embed_query = AsyncMock(return_value=[0.1])
            fake_vector = AsyncMock(return_value=[])
            monkeypatch.setattr(mod, "vector_search", fake_vector)
            monkeypatch.setattr(mod, "make_provider", lambda **_: fake_provider)
            monkeypatch.setattr(mod, "is_vault_ref", lambda _: False)

            result = await mod.rag_search(
                query="test", top_k=5, min_score=0.3,
                enrichment_keys=None, scope="raw_only",
            )
            assert "Aucun résultat" in result
            call_kwargs = fake_vector.call_args.kwargs
            assert call_kwargs["scope"] == "raw_only"
        finally:
            _ws_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_rag_search_enrichment_hit_labeled(self, monkeypatch):
        from rag.api import mcp_standard as mod
        from rag.api.mcp_standard import _ws_ctx
        from rag.schemas.mcp import SearchHit

        ws_id = uuid4()
        pool = MagicMock()
        pool_registry = MagicMock()
        pool_registry.get_workspace_pool = AsyncMock(return_value=MagicMock())
        ctx = _WsCtx(
            workspace_name="ws", rag_cnx="dsn", indexer_service="openai",
            indexer_provider="openai", indexer_model="m",
            indexer_api_key_ref=None, indexer_base_url=None,
            pool_registry=pool_registry, resolver=MagicMock(),
            workspace_id=ws_id, config_pool=pool,
        )
        token = _ws_ctx.set(ctx)
        try:
            fake_hit = SearchHit(
                workspace="ws", indexer="openai/m",
                path="src/a.py::public_functions", chunk_index=0,
                content="fn_a, fn_b", score=0.9,
                enrichment_key="public_functions", source_path="src/a.py",
            )
            fake_provider = MagicMock()
            fake_provider.embed_query = AsyncMock(return_value=[0.1])
            monkeypatch.setattr(mod, "vector_search", AsyncMock(return_value=[fake_hit]))
            monkeypatch.setattr(mod, "make_provider", lambda **_: fake_provider)
            monkeypatch.setattr(mod, "is_vault_ref", lambda _: False)

            result = await mod.rag_search(query="test", top_k=5, min_score=0.3)
            # Le hit d'enrichissement doit apparaître avec son étiquette
            assert "public_functions" in result
            assert "src/a.py" in result
        finally:
            _ws_ctx.reset(token)


class TestGetEnrichmentTool:
    @pytest.mark.asyncio
    async def test_get_enrichment_returns_result(self, monkeypatch):
        from rag.api import mcp_standard as mod
        from rag.api.mcp_standard import _ws_ctx

        ws_id = uuid4()
        pool = MagicMock()
        ctx = _WsCtx(
            workspace_name="ws", rag_cnx="dsn", indexer_service="openai",
            indexer_provider="openai", indexer_model="m",
            indexer_api_key_ref=None, indexer_base_url=None,
            pool_registry=MagicMock(), resolver=MagicMock(),
            workspace_id=ws_id, config_pool=pool,
        )
        token = _ws_ctx.set(ctx)
        try:
            monkeypatch.setattr(
                mod, "get_enrichment_db",
                AsyncMock(return_value={
                    "result": "fn_a, fn_b",
                    "result_type": "text",
                    "result_schema": None,
                }),
            )
            result = await mod.get_enrichment(path="src/a.py", key="public_functions")
            assert "fn_a" in result
        finally:
            _ws_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_get_enrichment_returns_not_found_message(self, monkeypatch):
        from rag.api import mcp_standard as mod
        from rag.api.mcp_standard import _ws_ctx

        ws_id = uuid4()
        pool = MagicMock()
        ctx = _WsCtx(
            workspace_name="ws", rag_cnx="dsn", indexer_service="openai",
            indexer_provider="openai", indexer_model="m",
            indexer_api_key_ref=None, indexer_base_url=None,
            pool_registry=MagicMock(), resolver=MagicMock(),
            workspace_id=ws_id, config_pool=pool,
        )
        token = _ws_ctx.set(ctx)
        try:
            monkeypatch.setattr(mod, "get_enrichment_db", AsyncMock(return_value=None))
            result = await mod.get_enrichment(path="src/a.py", key="nonexistent")
            assert "nonexistent" in result or "Aucun" in result
        finally:
            _ws_ctx.reset(token)
