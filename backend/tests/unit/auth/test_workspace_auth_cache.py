from __future__ import annotations

# Tests unitaires pour ApiKeyCache (T1 -- process-lifetime, pas de TTL/LRU).
# L'ancienne API (max_size, ttl_seconds, get(ws, key) -> _CacheEntry) a ete
# remplacee en T1 par un cache process-lifetime simple :
#   get(ref: str) -> str | None
#   put(ref: str, value: str) -> None
#   invalidate(ref: str) -> None
# Les tests TTL/LRU correspondants sont maintenant dans test_apikey_cache.py.
from rag.auth.workspace_auth import ApiKeyCache


def test_get_returns_none_on_miss() -> None:
    cache = ApiKeyCache()
    assert cache.get("${vault://rag:ws_a}") is None


def test_put_then_get_returns_value() -> None:
    cache = ApiKeyCache()
    cache.put("${vault://rag:ws_a}", "api-key-value")
    assert cache.get("${vault://rag:ws_a}") == "api-key-value"


def test_put_overwrites_existing_entry() -> None:
    cache = ApiKeyCache()
    cache.put("${vault://rag:ws_a}", "v1")
    cache.put("${vault://rag:ws_a}", "v2")
    assert cache.get("${vault://rag:ws_a}") == "v2"


def test_invalidate_removes_entry() -> None:
    cache = ApiKeyCache()
    cache.put("${vault://rag:ws_a}", "v")
    cache.invalidate("${vault://rag:ws_a}")
    assert cache.get("${vault://rag:ws_a}") is None


def test_invalidate_only_removes_named_ref() -> None:
    cache = ApiKeyCache()
    cache.put("${vault://rag:ws_a}", "v_a")
    cache.put("${vault://rag:ws_b}", "v_b")
    cache.invalidate("${vault://rag:ws_a}")
    assert cache.get("${vault://rag:ws_a}") is None
    assert cache.get("${vault://rag:ws_b}") == "v_b"


def test_invalidate_unknown_ref_is_noop() -> None:
    cache = ApiKeyCache()
    cache.put("${vault://rag:ws}", "v")
    cache.invalidate("${vault://rag:unknown}")
    assert cache.get("${vault://rag:ws}") == "v"
