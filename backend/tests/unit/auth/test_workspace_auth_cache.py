from __future__ import annotations

import time
from uuid import uuid4

from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry


def _entry() -> _CacheEntry:
    return _CacheEntry(
        workspace_id=uuid4(),
        indexer_used="openai/text-embedding-3-small",
        inserted_at=time.monotonic(),
    )


def test_get_returns_none_on_miss() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    assert cache.get("ws", "key") is None


def test_put_then_get_returns_entry() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    e = _entry()
    cache.put("ws", "key", e)
    got = cache.get("ws", "key")
    assert got is e


def test_ttl_expired_returns_none() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    stale = _CacheEntry(
        workspace_id=uuid4(),
        indexer_used="openai/m",
        inserted_at=time.monotonic() - 120,
    )
    cache.put("ws", "key", stale)
    assert cache.get("ws", "key") is None


def test_lru_eviction_when_over_capacity() -> None:
    cache = ApiKeyCache(max_size=2, ttl_seconds=60)
    e1 = _entry()
    e2 = _entry()
    e3 = _entry()
    cache.put("ws", "k1", e1)
    cache.put("ws", "k2", e2)
    cache.put("ws", "k3", e3)  # évincte k1 (le plus ancien)
    assert cache.get("ws", "k1") is None
    assert cache.get("ws", "k2") is e2
    assert cache.get("ws", "k3") is e3


def test_get_promotes_entry_to_most_recent() -> None:
    cache = ApiKeyCache(max_size=2, ttl_seconds=60)
    e1 = _entry()
    e2 = _entry()
    cache.put("ws", "k1", e1)
    cache.put("ws", "k2", e2)
    # accès à k1 le rend le plus récent ; l'insertion suivante doit évincter k2
    assert cache.get("ws", "k1") is e1
    e3 = _entry()
    cache.put("ws", "k3", e3)
    assert cache.get("ws", "k2") is None
    assert cache.get("ws", "k1") is e1


def test_invalidate_removes_only_named_workspace_entries() -> None:
    cache = ApiKeyCache(max_size=8, ttl_seconds=60)
    e_a, e_b = _entry(), _entry()
    cache.put("ws_a", "k", e_a)
    cache.put("ws_b", "k", e_b)
    cache.invalidate("ws_a")
    assert cache.get("ws_a", "k") is None
    assert cache.get("ws_b", "k") is e_b


def test_invalidate_unknown_workspace_is_noop() -> None:
    cache = ApiKeyCache(max_size=4, ttl_seconds=60)
    e = _entry()
    cache.put("ws", "k", e)
    cache.invalidate("unknown_ws")
    assert cache.get("ws", "k") is e
