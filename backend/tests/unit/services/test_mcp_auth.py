from __future__ import annotations

# Tests unitaires pour _authenticate et _load_workspace_context.
# Après T7 : _authenticate utilise fingerprint+cache+Harpocrate resolver.
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache
from rag.services.mcp import McpWorkspaceRef, _authenticate, _load_workspace_context


class _StubResolver:
    def __init__(self, value: str) -> None:
        self._value = value

    async def resolve_with_retry(self, ref: str) -> str:
        return self._value


@pytest.mark.asyncio
async def test_authenticate_workspace_not_found_raises_error() -> None:
    """fetchrow None + workspace absent (fetchval None) → WorkspaceNotFound."""
    cache = ApiKeyCache()
    pool = MagicMock()
    # Premier fetchrow (fingerprint lookup) → None
    pool.fetchrow = AsyncMock(return_value=None)
    # fetchval (exists check) → None : workspace inconnu
    pool.fetchval = AsyncMock(return_value=None)

    ref = McpWorkspaceRef(name="ghost", api_key="x")
    with pytest.raises(WorkspaceNotFound):
        await _authenticate(
            ref=ref,
            config_pool=pool,
            apikey_cache=cache,
            secret_resolver=_StubResolver("x"),
        )


@pytest.mark.asyncio
async def test_authenticate_bad_key_raises_401() -> None:
    """Fingerprint ne matche pas mais workspace existe → 401."""
    cache = ApiKeyCache()
    pool = MagicMock()
    # fetchrow → None (fingerprint ne matche pas)
    pool.fetchrow = AsyncMock(return_value=None)
    # fetchval → 1 (workspace existe)
    pool.fetchval = AsyncMock(return_value=1)

    ref = McpWorkspaceRef(name="ws", api_key="wrong-key")
    with pytest.raises(HTTPException) as exc:
        await _authenticate(
            ref=ref,
            config_pool=pool,
            apikey_cache=cache,
            secret_resolver=_StubResolver("wrong-key"),
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_authenticate_valid_key_returns_entry() -> None:
    """Fingerprint matche + resolver retourne la bonne clé → _CacheEntry."""
    cache = ApiKeyCache()
    ws_id = uuid4()
    good_key = "good-key"
    api_key_ref = "${vault://test:ws_apikey}"

    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "api_key_ref": api_key_ref,
            "indexer_used": "voyage/voyage-3-lite",
        }
    )
    pool.fetchval = AsyncMock(return_value=None)  # jamais appelé si fetchrow réussit

    ref = McpWorkspaceRef(name="ws", api_key=good_key)
    entry = await _authenticate(
        ref=ref,
        config_pool=pool,
        apikey_cache=cache,
        secret_resolver=_StubResolver(good_key),
    )
    assert entry.workspace_id == ws_id
    assert entry.indexer_used == "voyage/voyage-3-lite"


@pytest.mark.asyncio
async def test_authenticate_cache_hit_skips_resolver() -> None:
    """Sur cache-hit, le resolver n'est pas appelé."""
    cache = ApiKeyCache()
    ws_id = uuid4()
    good_key = "cached-key"
    api_key_ref = "${vault://test:ws_apikey}"
    # Pré-populer le cache
    cache.put(api_key_ref, good_key)

    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "api_key_ref": api_key_ref,
            "indexer_used": "openai/m",
        }
    )
    pool.fetchval = AsyncMock(return_value=None)

    resolver = MagicMock()
    resolver.resolve_with_retry = AsyncMock(side_effect=AssertionError("should not be called"))

    ref = McpWorkspaceRef(name="ws", api_key=good_key)
    entry = await _authenticate(
        ref=ref,
        config_pool=pool,
        apikey_cache=cache,
        secret_resolver=resolver,  # type: ignore[arg-type]
    )
    assert entry.workspace_id == ws_id
    resolver.resolve_with_retry.assert_not_called()


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


@pytest.mark.asyncio
async def test_load_workspace_context_missing_workspace_raises_runtime() -> None:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError):
        await _load_workspace_context(pool, "ghost")
