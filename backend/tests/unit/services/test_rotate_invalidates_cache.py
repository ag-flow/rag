from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.services.workspaces import rotate_apikey


@pytest.mark.asyncio
async def test_rotate_apikey_calls_invalidate_on_cache(monkeypatch) -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    cache.put(
        "ws_x",
        "old-key",
        _CacheEntry(
            workspace_id=uuid4(),
            indexer_used="openai/m",
            inserted_at=time.monotonic(),
        ),
    )

    pool = MagicMock()
    pool.execute = AsyncMock()
    # rotate_apikey utilise `fetch_one(pool, ...)` du module db.pool — qui
    # appelle pool.acquire().__aenter__().fetchrow(...). On stub :
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    conn.execute = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    await rotate_apikey(name="ws_x", config_pool=pool, apikey_cache=cache)

    assert cache.get("ws_x", "old-key") is None


@pytest.mark.asyncio
async def test_rotate_apikey_works_without_cache_kwarg() -> None:
    """Rétro-compat : appelable sans `apikey_cache=` (None par défaut)."""
    pool = MagicMock()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    conn.execute = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    # Ne doit pas lever
    await rotate_apikey(name="ws_x", config_pool=pool)
