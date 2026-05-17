from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from rag.auth.workspace_auth import (
    ApiKeyCache,
    AuthContext,
    _CacheEntry,
    require_workspace_apikey,
)

_DEK = "x" * 32


def _fake_request(headers: dict[str, str], pool, cache: ApiKeyCache):
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(
            state=SimpleNamespace(
                apikey_cache=cache,
                pools=SimpleNamespace(config_pool=pool),
                settings=SimpleNamespace(api_key_dek=_DEK),
            )
        ),
    )


@pytest.mark.asyncio
async def test_missing_authorization_header_raises_401() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    req = _fake_request({}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "missing_bearer_token"


@pytest.mark.asyncio
async def test_wrong_scheme_raises_401() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    req = _fake_request({"Authorization": "Basic abc"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_auth_scheme"


@pytest.mark.asyncio
async def test_cache_hit_returns_auth_context_without_db() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    cache.put(
        "ws",
        "api-key-xyz",
        _CacheEntry(
            workspace_id=ws_id,
            indexer_used="openai/text-embedding-3-small",
            inserted_at=time.monotonic(),
        ),
    )

    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=AssertionError("pool must not be called on cache hit"))

    req = _fake_request({"Authorization": "Bearer api-key-xyz"}, pool, cache)
    ctx = await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert isinstance(ctx, AuthContext)
    assert ctx.workspace_id == ws_id
    assert ctx.indexer_used == "openai/text-embedding-3-small"


@pytest.mark.asyncio
async def test_cache_miss_workspace_not_found_raises_401() -> None:
    """Workspace inconnu → 401 uniforme (ne révèle pas l'existence)."""
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    req = _fake_request({"Authorization": "Bearer some-key"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ghost", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"


@pytest.mark.asyncio
async def test_cache_miss_invalid_key_raises_401() -> None:
    """compare_digest échoue (stored != présenté) → 401."""
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "stored": "the-real-stored-key",
            "indexer_used": "openai/text-embedding-3-small",
        }
    )

    req = _fake_request({"Authorization": "Bearer bad-key"}, pool, cache)
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_workspace_apikey"
    assert cache.get("ws", "bad-key") is None  # mauvaise clé non cachée


@pytest.mark.asyncio
async def test_cache_miss_valid_key_populates_cache() -> None:
    """compare_digest réussit → AuthContext retourné, entrée mise en cache."""
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    ws_id = uuid4()
    good_key = "good-key"
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value={
            "id": ws_id,
            "stored": good_key,
            "indexer_used": "voyage/voyage-3-lite",
        }
    )

    req = _fake_request({"Authorization": f"Bearer {good_key}"}, pool, cache)
    ctx = await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert ctx.workspace_id == ws_id
    assert ctx.indexer_used == "voyage/voyage-3-lite"
    cached = cache.get("ws", good_key)
    assert cached is not None
    assert cached.workspace_id == ws_id


@pytest.mark.asyncio
async def test_dek_absent_raises_503() -> None:
    """Si api_key_dek est None en settings → 503 avant tout accès DB."""
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(side_effect=AssertionError("pool must not be called when DEK absent"))

    req = SimpleNamespace(
        headers={"Authorization": "Bearer some-key"},
        app=SimpleNamespace(
            state=SimpleNamespace(
                apikey_cache=cache,
                pools=SimpleNamespace(config_pool=pool),
                settings=SimpleNamespace(api_key_dek=None),
            )
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await require_workspace_apikey("ws", req)  # type: ignore[arg-type]
    assert exc.value.status_code == 503
    assert exc.value.detail == "api_key_dek_unavailable"
