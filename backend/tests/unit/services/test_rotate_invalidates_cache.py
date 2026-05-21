from __future__ import annotations

# Tests unitaires pour rotate_apikey et invalidation cache (T1).
# NOTE(T5): apikey_cache.invalidate() recoit le name du workspace pour l'instant
# (pas encore la ref vault complete). Refactore en T5.
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from rag.auth.workspace_auth import ApiKeyCache
from rag.services.workspaces import rotate_apikey


@pytest.mark.asyncio
async def test_rotate_apikey_calls_invalidate_on_cache(monkeypatch) -> None:
    """rotate_apikey appelle cache.invalidate(name) apres rotation."""
    cache = ApiKeyCache()
    # Pre-popule avec la ref vault (T5 utilisera la vraie ref)
    # Pour l'instant on teste juste que invalidate est appele
    invalidate_calls: list[str] = []
    original_invalidate = cache.invalidate

    def _track_invalidate(ref: str) -> None:
        invalidate_calls.append(ref)
        original_invalidate(ref)

    monkeypatch.setattr(cache, "invalidate", _track_invalidate)

    pool = MagicMock()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    conn.execute = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    await rotate_apikey(name="ws_x", config_pool=pool, apikey_cache=cache, api_key_dek="x" * 32)

    assert len(invalidate_calls) == 1
    assert invalidate_calls[0] == "ws_x"


@pytest.mark.asyncio
async def test_rotate_apikey_works_without_cache_kwarg() -> None:
    """Retro-compat : appelable sans `apikey_cache=` (None par defaut)."""
    pool = MagicMock()
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    conn.execute = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    # Ne doit pas lever
    await rotate_apikey(name="ws_x", config_pool=pool, api_key_dek="x" * 32)
