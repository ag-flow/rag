from __future__ import annotations

import time

import pytest

from rag.secrets.resolver import SecretResolver, VaultLookupFailed


class CountingFakeClient:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls = 0
        self.fail_until_invalidate = False

    def get_secret(self, path: str) -> str:
        self.calls += 1
        if self.fail_until_invalidate:
            raise PermissionError("401")
        return self.value


def test_cache_hit_avoids_second_lookup() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=60)

    assert r.resolve("${vault://api1:k}") == "v"
    assert r.resolve("${vault://api1:k}") == "v"
    assert client.calls == 1


def test_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=10)

    now = [time.monotonic()]
    monkeypatch.setattr("rag.secrets.resolver.time.monotonic", lambda: now[0])

    r.resolve("${vault://api1:k}")
    now[0] += 5
    r.resolve("${vault://api1:k}")
    assert client.calls == 1

    now[0] += 6  # total 11 > ttl 10
    r.resolve("${vault://api1:k}")
    assert client.calls == 2


def test_invalidate_clears_specific_ref() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=300)

    r.resolve("${vault://api1:k}")
    r.invalidate("${vault://api1:k}")
    r.resolve("${vault://api1:k}")
    assert client.calls == 2


def test_invalidate_unknown_ref_is_silent() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=300)
    r.invalidate("${vault://api1:not_cached}")  # ne lève rien


def test_clear_cache_empties_all() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=300)
    r.resolve("${vault://api1:a}")
    r.resolve("${vault://api1:b}")
    assert client.calls == 2
    r.clear_cache()
    r.resolve("${vault://api1:a}")
    r.resolve("${vault://api1:b}")
    assert client.calls == 4


def test_resolve_with_retry_after_401_invalidates_and_retries() -> None:
    client = CountingFakeClient("v")
    r = SecretResolver(harpocrate_clients={"api1": client}, cache_ttl=300)

    r.resolve("${vault://api1:k}")  # cached
    assert client.calls == 1

    # Simule un 401 sur le prochain lookup en forçant un nouvel appel
    client.fail_until_invalidate = True
    with pytest.raises(VaultLookupFailed):
        r.resolve_with_retry("${vault://api1:k}")

    # Après échec persistant : 1 succès initial + (1 invalidate + 1 retry) = au moins 2 calls
    assert client.calls >= 2


def test_resolve_with_retry_succeeds_after_one_retry() -> None:
    """Si le 401 disparaît au retry, on retourne la valeur."""

    class FlippyClient:
        def __init__(self, value: str) -> None:
            self.value = value
            self.calls = 0

        def get_secret(self, path: str) -> str:
            self.calls += 1
            if self.calls == 2:  # 1ère cached, 2e en retry après invalidate
                return self.value
            if self.calls == 1:
                return self.value
            return self.value

    # On utilise plutôt un client qui échoue puis réussit
    class FailThenOk:
        def __init__(self) -> None:
            self.calls = 0

        def get_secret(self, path: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise PermissionError("401")
            return "ok"

    r = SecretResolver(harpocrate_clients={"api1": FailThenOk()}, cache_ttl=300)
    # Première tentative échoue → invalidate → retry réussit
    assert r.resolve_with_retry("${vault://api1:k}") == "ok"
