from __future__ import annotations

from rag.auth.workspace_auth import ApiKeyCache


def test_cache_put_then_get_returns_value() -> None:
    cache = ApiKeyCache()
    cache.put("${vault://rag:wsapi_test1}", "secret-value-1")
    assert cache.get("${vault://rag:wsapi_test1}") == "secret-value-1"


def test_cache_unknown_ref_returns_none() -> None:
    cache = ApiKeyCache()
    assert cache.get("${vault://rag:unknown}") is None


def test_cache_no_ttl_value_persists() -> None:
    """Pas de TTL : valeur survit indéfiniment dans le process."""
    cache = ApiKeyCache()
    cache.put("${vault://rag:wsapi_x}", "v")
    for _ in range(100):
        assert cache.get("${vault://rag:wsapi_x}") == "v"


def test_cache_invalidate_evicts_entry() -> None:
    cache = ApiKeyCache()
    cache.put("${vault://rag:wsapi_x}", "v")
    cache.invalidate("${vault://rag:wsapi_x}")
    assert cache.get("${vault://rag:wsapi_x}") is None


def test_cache_invalidate_unknown_ref_no_error() -> None:
    """invalidate sur clé inexistante est idempotent."""
    cache = ApiKeyCache()
    cache.invalidate("${vault://rag:never_put}")  # ne doit pas lever
