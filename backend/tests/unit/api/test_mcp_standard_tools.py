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


def _make_ctx(config_pool=None, pool_registry=None, *, scope="read", ws_id=None) -> _KeyCtx:
    ws_id = ws_id or uuid4()
    config_pool = config_pool or MagicMock()
    # _resolve_ws lit la config du workspace par son slug via fetchrow.
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


# ── index_status ─────────────────────────────────────────────────────────────


class TestIndexStatusTool:
    @pytest.mark.asyncio
    async def test_global_returns_json_with_workspace_name(self, monkeypatch):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx()
        monkeypatch.setattr(
            "rag.db.mcp_tools.get_index_status",
            AsyncMock(return_value={
                "documents_count": 7,
                "last_indexed_at": "2026-01-01T00:00:00",
                "sync": {"healthy": True, "last_job_status": "done",
                         "last_indexed_at": None, "next_sync_at": None,
                         "last_job_finished_at": None},
            }),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.index_status("ws")
        finally:
            _ws_ctx.reset(tok)

        assert "ws" in result
        assert "7" in result
        assert "healthy" in result

    @pytest.mark.asyncio
    async def test_with_path_found_returns_doc_info(self, monkeypatch):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx()
        monkeypatch.setattr(
            "rag.db.mcp_tools.get_document_status",
            AsyncMock(return_value={
                "path": "src/auth.py",
                "content_hash": "sha256:abc",
                "indexed_at": "2026-01-01",
                "indexer_used": "openai/m",
                "title": None,
            }),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.index_status("ws", path="src/auth.py")
        finally:
            _ws_ctx.reset(tok)

        assert "sha256:abc" in result
        assert "src/auth.py" in result

    @pytest.mark.asyncio
    async def test_with_path_not_found_returns_error_message(self, monkeypatch):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx()
        monkeypatch.setattr(
            "rag.db.mcp_tools.get_document_status",
            AsyncMock(return_value=None),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.index_status("ws", path="missing.py")
        finally:
            _ws_ctx.reset(tok)

        assert "missing.py" in result
        assert "non trouvé" in result.lower() or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_unknown_workspace_returns_help_message(self):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx()
        ctx.config_pool.fetchrow = AsyncMock(return_value=None)
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.index_status("inconnu")
        finally:
            _ws_ctx.reset(tok)

        assert "inconnu" in result
        assert "list_workspaces" in result


# ── search_files ─────────────────────────────────────────────────────────────


class TestSearchFilesTool:
    def _pool_registry(self):
        ws_pool = MagicMock()
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=ws_pool)
        return registry, ws_pool

    @pytest.mark.asyncio
    async def test_no_hits_returns_not_found_message(self, monkeypatch):
        from rag.api import mcp_standard as mod

        registry, _ = self._pool_registry()
        ctx = _make_ctx(pool_registry=registry)
        monkeypatch.setattr(
            "rag.db.mcp_tools.search_files_in_workspace",
            AsyncMock(return_value=[]),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.search_files("ws", pattern="RAG_MASTER_KEY")
        finally:
            _ws_ctx.reset(tok)

        assert "RAG_MASTER_KEY" in result
        assert "Aucune" in result

    @pytest.mark.asyncio
    async def test_hits_include_path_and_content(self, monkeypatch):
        from rag.api import mcp_standard as mod

        registry, _ = self._pool_registry()
        ctx = _make_ctx(pool_registry=registry)
        monkeypatch.setattr(
            "rag.db.mcp_tools.search_files_in_workspace",
            AsyncMock(return_value=[
                {"path": "src/config.py", "chunk_index": 2,
                 "content": "RAG_MASTER_KEY = os.getenv(...)",
                 "enrichment_key": None, "source_path": None},
            ]),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.search_files("ws", pattern="RAG_MASTER_KEY")
        finally:
            _ws_ctx.reset(tok)

        assert "src/config.py" in result
        assert "RAG_MASTER_KEY" in result

    @pytest.mark.asyncio
    async def test_enriched_hit_uses_source_path_label(self, monkeypatch):
        from rag.api import mcp_standard as mod

        registry, _ = self._pool_registry()
        ctx = _make_ctx(pool_registry=registry)
        monkeypatch.setattr(
            "rag.db.mcp_tools.search_files_in_workspace",
            AsyncMock(return_value=[
                {"path": "src/a.py::public_functions", "chunk_index": 0,
                 "content": "fn_a, fn_b",
                 "enrichment_key": "public_functions", "source_path": "src/a.py"},
            ]),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.search_files("ws", pattern="fn_a")
        finally:
            _ws_ctx.reset(tok)

        assert "src/a.py" in result
        assert "public_functions" in result

    @pytest.mark.asyncio
    async def test_count_displayed_in_header(self, monkeypatch):
        from rag.api import mcp_standard as mod

        registry, _ = self._pool_registry()
        ctx = _make_ctx(pool_registry=registry)
        hits = [
            {"path": f"file{i}.py", "chunk_index": 0, "content": "x",
             "enrichment_key": None, "source_path": None}
            for i in range(3)
        ]
        monkeypatch.setattr(
            "rag.db.mcp_tools.search_files_in_workspace",
            AsyncMock(return_value=hits),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.search_files("ws", pattern="x")
        finally:
            _ws_ctx.reset(tok)

        assert "3" in result


# ── get_document ─────────────────────────────────────────────────────────────


class TestGetDocumentTool:
    def _pool_registry(self):
        registry = MagicMock()
        registry.get_workspace_pool = AsyncMock(return_value=MagicMock())
        return registry

    @pytest.mark.asyncio
    async def test_allow_full_read_false_returns_refusal(self, monkeypatch):
        from rag.api import mcp_standard as mod

        config_pool = MagicMock()
        config_pool.fetchval = AsyncMock(return_value=False)
        ctx = _make_ctx(config_pool=config_pool, pool_registry=self._pool_registry())
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.get_document("ws", path="secret.md")
        finally:
            _ws_ctx.reset(tok)

        assert "rag_search" in result.lower() or "non autorisée" in result.lower()

    @pytest.mark.asyncio
    async def test_path_not_indexed_returns_error_message(self, monkeypatch):
        from rag.api import mcp_standard as mod

        config_pool = MagicMock()
        config_pool.fetchval = AsyncMock(return_value=True)
        ctx = _make_ctx(config_pool=config_pool, pool_registry=self._pool_registry())
        monkeypatch.setattr(
            "rag.db.mcp_tools.reconstruct_document",
            AsyncMock(return_value=None),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.get_document("ws", path="absent.md")
        finally:
            _ws_ctx.reset(tok)

        assert "absent.md" in result
        assert "non trouvé" in result.lower() or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_prose_document_returns_content(self, monkeypatch):
        from rag.api import mcp_standard as mod

        config_pool = MagicMock()
        config_pool.fetchval = AsyncMock(return_value=True)
        ctx = _make_ctx(config_pool=config_pool, pool_registry=self._pool_registry())
        monkeypatch.setattr(
            "rag.db.mcp_tools.reconstruct_document",
            AsyncMock(return_value={
                "content": "# Intro\n\nLorem ipsum.",
                "is_legacy": False,
                "is_code_structured": False,
                "sections_count": 2,
            }),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.get_document("ws", path="docs/intro.md")
        finally:
            _ws_ctx.reset(tok)

        assert "docs/intro.md" in result
        assert "Lorem ipsum" in result
        assert "2 section" in result

    @pytest.mark.asyncio
    async def test_code_document_signals_symbol_reconstruction(self, monkeypatch):
        from rag.api import mcp_standard as mod

        config_pool = MagicMock()
        config_pool.fetchval = AsyncMock(return_value=True)
        ctx = _make_ctx(config_pool=config_pool, pool_registry=self._pool_registry())
        monkeypatch.setattr(
            "rag.db.mcp_tools.reconstruct_document",
            AsyncMock(return_value={
                "content": "def foo(): pass\n\nclass Bar: pass",
                "is_legacy": False,
                "is_code_structured": True,
                "sections_count": 2,
            }),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.get_document("ws", path="src/core.py")
        finally:
            _ws_ctx.reset(tok)

        assert "symboles" in result.lower() or "symbol" in result.lower()

    @pytest.mark.asyncio
    async def test_legacy_document_signals_legacy_engine(self, monkeypatch):
        from rag.api import mcp_standard as mod

        config_pool = MagicMock()
        config_pool.fetchval = AsyncMock(return_value=True)
        ctx = _make_ctx(config_pool=config_pool, pool_registry=self._pool_registry())
        monkeypatch.setattr(
            "rag.db.mcp_tools.reconstruct_document",
            AsyncMock(return_value={
                "content": "chunk 0\n\nchunk 1",
                "is_legacy": True,
                "is_code_structured": False,
                "sections_count": 2,
            }),
        )
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.get_document("ws", path="old.py")
        finally:
            _ws_ctx.reset(tok)

        assert "legacy" in result.lower()


# ── list_workspaces ──────────────────────────────────────────────────────────


class TestListWorkspacesTool:
    @pytest.mark.asyncio
    async def test_returns_scope_and_workspaces_json(self):
        from rag.api import mcp_standard as mod

        ctx = _make_ctx(scope="admin")
        ctx.config_pool.fetch = AsyncMock(return_value=[
            {"name": "ws-a", "label": "Workspace A", "description": "corpus A"},
            {"name": "ws-b", "label": None, "description": None},
        ])
        tok = _ws_ctx.set(ctx)
        try:
            result = await mod.list_workspaces()
        finally:
            _ws_ctx.reset(tok)

        import json as _json

        data = _json.loads(result)
        assert data["scope"] == "admin"
        slugs = {w["slug"] for w in data["workspaces"]}
        assert slugs == {"ws-a", "ws-b"}
        first = next(w for w in data["workspaces"] if w["slug"] == "ws-a")
        assert first["nom"] == "Workspace A"
        assert first["description"] == "corpus A"
        # label absent → repli sur le slug ; description absente → chaîne vide
        second = next(w for w in data["workspaces"] if w["slug"] == "ws-b")
        assert second["nom"] == "ws-b"
        assert second["description"] == ""
