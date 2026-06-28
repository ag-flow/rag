from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestGetIndexStatus:
    @pytest.mark.asyncio
    async def test_returns_workspace_aggregate(self):
        from rag.db.mcp_tools import get_index_status

        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                # indexed_documents aggregate
                {"documents_count": 42, "last_indexed_at": "2026-01-01T00:00:00Z"},
                # workspace_sources sync
                {"last_indexed_at": "2026-01-01T00:00:00Z", "next_sync_at": None},
                # last index_job
                {"status": "done", "finished_at": "2026-01-01T01:00:00Z"},
            ]
        )
        result = await get_index_status(pool, workspace_id=ws_id)
        assert result["documents_count"] == 42
        assert "sync" in result
        assert result["sync"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_healthy_false_when_last_job_error(self):
        from rag.db.mcp_tools import get_index_status

        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"documents_count": 10, "last_indexed_at": None},
                {"last_indexed_at": None, "next_sync_at": None},
                {"status": "error", "finished_at": "2026-01-01T01:00:00Z"},
            ]
        )
        result = await get_index_status(pool, workspace_id=ws_id)
        assert result["sync"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_healthy_true_when_no_job_yet(self):
        from rag.db.mcp_tools import get_index_status

        ws_id = uuid4()
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            side_effect=[
                {"documents_count": 0, "last_indexed_at": None},
                {"last_indexed_at": None, "next_sync_at": None},
                None,  # pas de job
            ]
        )
        result = await get_index_status(pool, workspace_id=ws_id)
        assert result["sync"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_get_document_status_returns_none_when_not_found(self):
        from rag.db.mcp_tools import get_document_status

        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        result = await get_document_status(pool, workspace_id=uuid4(), path="a.py")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_document_status_returns_doc_info(self):
        from rag.db.mcp_tools import get_document_status

        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value={
            "path": "a.py",
            "content_hash": "sha256:abc",
            "indexed_at": "2026-01-01",
            "indexer_used": "openai/m",
            "title": None,
        })
        result = await get_document_status(pool, workspace_id=uuid4(), path="a.py")
        assert result is not None
        assert result["path"] == "a.py"
        assert result["content_hash"] == "sha256:abc"


class TestSearchFilesInWorkspace:
    def _make_ws_pool(self, rows: list[dict]) -> MagicMock:
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=rows)
        conn.__aenter__ = AsyncMock(return_value=conn)
        conn.__aexit__ = AsyncMock(return_value=False)
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=conn)
        return pool

    @pytest.mark.asyncio
    async def test_exact_mode_returns_hits(self):
        from rag.db.mcp_tools import search_files_in_workspace

        rows = [{"path": "a.py", "content": "RAG_MASTER_KEY env var", "chunk_index": 0, "metadata": None}]
        pool = self._make_ws_pool(rows)
        hits = await search_files_in_workspace(pool, pattern="RAG_MASTER_KEY", mode="exact", top_k=10)
        assert len(hits) == 1
        assert hits[0]["path"] == "a.py"

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self):
        from rag.db.mcp_tools import search_files_in_workspace

        pool = self._make_ws_pool([])
        hits = await search_files_in_workspace(pool, pattern="notfound", mode="substring", top_k=5)
        assert hits == []

    @pytest.mark.asyncio
    async def test_regex_mode_uses_tilde_operator(self):
        from rag.db.mcp_tools import search_files_in_workspace

        pool = self._make_ws_pool([])
        await search_files_in_workspace(pool, pattern="def .+:", mode="regex", top_k=5)
        conn = pool.acquire.return_value.__aenter__.return_value
        sql = conn.fetch.call_args[0][0]
        assert "~" in sql

    @pytest.mark.asyncio
    async def test_exact_mode_uses_content_tsv(self):
        from rag.db.mcp_tools import search_files_in_workspace

        pool = self._make_ws_pool([])
        await search_files_in_workspace(pool, pattern="mytoken", mode="exact", top_k=5)
        conn = pool.acquire.return_value.__aenter__.return_value
        sql = conn.fetch.call_args[0][0]
        assert "content_tsv" in sql or "websearch_to_tsquery" in sql
