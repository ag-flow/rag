from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.db.enrichment_lookup import get_enrichment


class TestGetEnrichment:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        result = await get_enrichment(pool, workspace_id=uuid4(), path="a.py", key="docs")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_text_result(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value={
            "result": "liste de fonctions",
            "result_type": "text",
            "result_schema": None,
        })
        result = await get_enrichment(pool, workspace_id=uuid4(), path="a.py", key="public_functions")
        assert result is not None
        assert result["result"] == "liste de fonctions"
        assert result["result_type"] == "text"
        assert result["result_schema"] is None

    @pytest.mark.asyncio
    async def test_returns_json_result(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value={
            "result": '["fn_a", "fn_b"]',
            "result_type": "json",
            "result_schema": '{"type": "array"}',
        })
        result = await get_enrichment(pool, workspace_id=uuid4(), path="a.py", key="public_functions")
        assert result is not None
        assert result["result_type"] == "json"
        assert result["result"] == '["fn_a", "fn_b"]'

    @pytest.mark.asyncio
    async def test_queries_document_enrichments_table(self):
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        ws_id = uuid4()
        await get_enrichment(pool, workspace_id=ws_id, path="src/x.py", key="deps")
        sql = pool.fetchrow.call_args[0][0]
        assert "document_enrichments" in sql
        assert "metadata_key" in sql
