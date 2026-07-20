from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from rag.api.mcp_standard import _KeyCtx, _ws_ctx


def _ws_row(ws_id: UUID) -> dict:
    """Ligne renvoyée par config_pool.fetchrow dans _resolve_ws."""
    return {
        "id": ws_id,
        "name": "ws",
        "rag_cnx": "dsn",
        "provider": "openai",
        "model": "m",
        "api_key_ref": None,
        "base_url": None,
        "service": "openai",
    }


def _make_ctx(*, pool_registry=None, ws_id=None, scope="read") -> _KeyCtx:
    ws_id = ws_id or uuid4()
    config_pool = MagicMock()
    config_pool.fetchrow = AsyncMock(return_value=_ws_row(ws_id))
    pool_registry = pool_registry or MagicMock()
    return _KeyCtx(
        owner_id="owner-1",
        scope=scope,
        config_pool=config_pool,
        pool_registry=pool_registry,
        resolver=MagicMock(),
        client_provider=MagicMock(),
        default_vault_name=None,
    )


class TestKeyCtx:
    def test_key_ctx_exposes_auth_fields(self):
        pool = MagicMock()
        ctx = _KeyCtx(
            owner_id="owner-1",
            scope="admin",
            config_pool=pool,
            pool_registry=MagicMock(),
            resolver=MagicMock(),
            client_provider=MagicMock(),
            default_vault_name=None,
        )
        assert ctx.owner_id == "owner-1"
        assert ctx.scope == "admin"
        assert ctx.config_pool is pool


class TestRagSearchEnrichmentParams:
    @pytest.mark.asyncio
    async def test_rag_search_accepts_scope_param(self, monkeypatch):
        from rag.api import mcp_standard as mod

        pool_registry = MagicMock()
        pool_registry.get_workspace_pool = AsyncMock(return_value=MagicMock())
        ctx = _make_ctx(pool_registry=pool_registry)
        token = _ws_ctx.set(ctx)
        try:
            fake_provider = MagicMock()
            fake_provider.embed_query = AsyncMock(return_value=[0.1])
            fake_vector = AsyncMock(return_value=[])
            monkeypatch.setattr(mod, "vector_search", fake_vector)
            monkeypatch.setattr(mod, "make_provider", lambda **_: fake_provider)
            monkeypatch.setattr(mod, "is_vault_ref", lambda _: False)

            result = await mod.rag_search(
                "ws", query="test", top_k=5, min_score=0.3,
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
        from rag.schemas.mcp import SearchHit

        pool_registry = MagicMock()
        pool_registry.get_workspace_pool = AsyncMock(return_value=MagicMock())
        ctx = _make_ctx(pool_registry=pool_registry)
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

            result = await mod.rag_search("ws", query="test", top_k=5, min_score=0.3)
            # Le hit d'enrichissement doit apparaître avec son étiquette
            assert "public_functions" in result
            assert "src/a.py" in result
        finally:
            _ws_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_rag_search_unknown_workspace_returns_help(self, monkeypatch):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx()
        ctx.config_pool.fetchrow = AsyncMock(return_value=None)
        token = _ws_ctx.set(ctx)
        try:
            result = await mod.rag_search("inconnu", query="test")
            assert "inconnu" in result
            assert "list_workspaces" in result
        finally:
            _ws_ctx.reset(token)


class TestGetEnrichmentTool:
    @pytest.mark.asyncio
    async def test_get_enrichment_returns_result(self, monkeypatch):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx()
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
            result = await mod.get_enrichment("ws", path="src/a.py", key="public_functions")
            assert "fn_a" in result
        finally:
            _ws_ctx.reset(token)

    @pytest.mark.asyncio
    async def test_get_enrichment_returns_not_found_message(self, monkeypatch):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx()
        token = _ws_ctx.set(ctx)
        try:
            monkeypatch.setattr(mod, "get_enrichment_db", AsyncMock(return_value=None))
            result = await mod.get_enrichment("ws", path="src/a.py", key="nonexistent")
            assert "nonexistent" in result or "Aucun" in result
        finally:
            _ws_ctx.reset(token)
