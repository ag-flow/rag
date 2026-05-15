from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.services.mcp import McpWorkspaceRef, _authenticate, _load_workspace_context


@pytest.mark.asyncio
async def test_authenticate_cache_hit_skips_db() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    cache.put(
        "ws",
        "key",
        _CacheEntry(
            workspace_id=ws_id,
            indexer_used="openai/m",
            inserted_at=time.monotonic(),
        ),
    )
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=AssertionError("DB not allowed on cache hit"))

    ref = McpWorkspaceRef(name="ws", api_key="key")
    entry = await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)
    assert entry.workspace_id == ws_id
    assert entry.indexer_used == "openai/m"


@pytest.mark.asyncio
async def test_authenticate_workspace_not_found_raises_404() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)

    ref = McpWorkspaceRef(name="ghost", api_key="x")
    with pytest.raises(WorkspaceNotFound):
        await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)


@pytest.mark.asyncio
async def test_authenticate_bad_bcrypt_raises_401(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "api_key_hash": "$2b$12$invalid",
            "indexer_used": "openai/m",
        }
    )

    from rag.services import mcp

    monkeypatch.setattr(mcp, "verify_api_key", lambda _k, _h: False)

    ref = McpWorkspaceRef(name="ws", api_key="wrong")
    with pytest.raises(HTTPException) as exc:
        await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"
    # Bad key NOT cached
    assert cache.get("ws", "wrong") is None


@pytest.mark.asyncio
async def test_authenticate_valid_bcrypt_populates_cache(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "api_key_hash": "$2b$12$valid",
            "indexer_used": "voyage/voyage-3-lite",
        }
    )

    from rag.services import mcp

    monkeypatch.setattr(mcp, "verify_api_key", lambda _k, _h: True)

    ref = McpWorkspaceRef(name="ws", api_key="good")
    entry = await _authenticate(ref=ref, config_pool=pool, apikey_cache=cache)
    assert entry.workspace_id == ws_id
    assert entry.indexer_used == "voyage/voyage-3-lite"
    cached = cache.get("ws", "good")
    assert cached is not None
    assert cached.workspace_id == ws_id


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
        }
    )
    ctx = await _load_workspace_context(pool, "ws")
    assert ctx["workspace_name"] == "ws"
    assert ctx["provider"] == "openai"
    assert ctx["api_key_ref"] == "openai_embedding_key"


@pytest.mark.asyncio
async def test_load_workspace_context_missing_workspace_raises_runtime() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError):
        await _load_workspace_context(pool, "ghost")
