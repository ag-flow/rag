from __future__ import annotations

# Tests unitaires pour _authenticate et _load_workspace_context.
# Clés utilisateur hash-only : lookup fingerprint + grant can_read, aucune
# résolution Harpocrate.
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.services.mcp import McpWorkspaceRef, _authenticate, _load_workspace_context


@pytest.mark.asyncio
async def test_authenticate_workspace_not_found_raises_error() -> None:
    """fetchrow None + workspace absent (fetchval None) → WorkspaceNotFound."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=None)

    ref = McpWorkspaceRef(name="ghost", api_key="x")
    with pytest.raises(WorkspaceNotFound):
        await _authenticate(ref=ref, config_pool=pool)


@pytest.mark.asyncio
async def test_authenticate_bad_key_or_missing_grant_raises_401() -> None:
    """Clé inconnue OU grant can_read absent, workspace existant → 401."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=1)

    ref = McpWorkspaceRef(name="ws", api_key="wrong-key")
    with pytest.raises(HTTPException) as exc:
        await _authenticate(ref=ref, config_pool=pool)
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_authenticate_valid_key_returns_entry() -> None:
    """Fingerprint + grant can_read matchent → _CacheEntry, un seul fetchrow."""
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={"id": ws_id, "indexer_used": "voyage/voyage-3-lite"}
    )
    pool.fetchval = AsyncMock(return_value=None)  # jamais appelé si fetchrow réussit

    ref = McpWorkspaceRef(name="ws", api_key="good-key")
    entry = await _authenticate(ref=ref, config_pool=pool)

    assert entry.workspace_id == ws_id
    assert entry.indexer_used == "voyage/voyage-3-lite"
    assert pool.fetchrow.await_count == 1
    sql = pool.fetchrow.await_args.args[0]
    assert "user_api_keys" in sql
    assert "can_read" in sql


@pytest.mark.asyncio
async def test_load_workspace_context_returns_full_row() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "workspace_name": "ws",
            "rag_cnx": "postgresql://...",
            "provider": "openai",
            "model": "text-embedding-3-small",
            "api_key_ref": "openai_embedding_key",
            "base_url": None,
            "service": "openai",
            "rerank_provider": None,
            "rerank_model": None,
            "rerank_api_key_ref": None,
            "rerank_base_url": None,
            "rerank_top_k_pre_rerank": None,
        }
    )
    ctx = await _load_workspace_context(pool, "ws")
    assert ctx["workspace_name"] == "ws"
    assert ctx["provider"] == "openai"
    assert ctx["api_key_ref"] == "openai_embedding_key"
    assert ctx["rerank"] is None


@pytest.mark.asyncio
async def test_load_workspace_context_missing_workspace_raises_runtime() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError):
        await _load_workspace_context(pool, "ghost")
