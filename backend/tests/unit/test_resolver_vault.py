from __future__ import annotations

import pytest

from rag.secrets.resolver import SecretResolver, VaultClient, VaultLookupFailed
from rag.secrets.vault import HarpocrateVaultClient


class FakeVaultClient:
    def __init__(self, secrets: dict[str, str]) -> None:
        self._secrets = secrets
        self.calls: list[str] = []

    def get_secret(self, path: str) -> str:
        self.calls.append(path)
        if path not in self._secrets:
            raise KeyError(f"secret not found: {path}")
        return self._secrets[path]


class FakeSecretNotFound(Exception):
    """Simule harpocrate.exceptions.SecretNotFound sans dépendre du SDK."""


class FakeVaultClientRaisesSecretNotFound:
    """Client vault dont get_secret lève FakeSecretNotFound (simule le SDK)."""

    def get_secret(self, path: str) -> str:
        raise FakeSecretNotFound(f"secret missing: {path}")


async def test_resolver_uses_correct_vault_client() -> None:
    api1 = FakeVaultClient({"shared/openai": "sk-real-from-api1"})
    api2 = FakeVaultClient({"shared/openai": "sk-real-from-api2"})

    r = SecretResolver(harpocrate_clients={"api1": api1, "api2": api2})

    assert await r.resolve("${vault://api1:shared/openai}") == "sk-real-from-api1"
    assert await r.resolve("${vault://api2:shared/openai}") == "sk-real-from-api2"
    assert api1.calls == ["shared/openai"]
    assert api2.calls == ["shared/openai"]


async def test_resolver_unknown_api_key_id() -> None:
    r = SecretResolver(harpocrate_clients={"api1": FakeVaultClient({})})
    with pytest.raises(VaultLookupFailed, match="unknown"):
        await r.resolve("${vault://unknown:foo}")


def test_harpocrate_client_implements_protocol() -> None:
    # Smoke : la classe satisfait le protocole VaultClient (structural typing).
    # On n'instancie pas — le SDK n'est pas installé sur Windows.
    assert hasattr(HarpocrateVaultClient, "get_secret")
    client_type: type[VaultClient] = HarpocrateVaultClient  # type assignable au Protocol
    assert client_type is HarpocrateVaultClient


# ---------------------------------------------------------------------------
# SecretNotFound (SDK) → VaultLookupFailed dans le resolver
# ---------------------------------------------------------------------------


async def test_resolver_secret_not_found_sdk_converted_to_vault_lookup_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SecretNotFound levé par le SDK doit être converti en VaultLookupFailed.

    Le resolver est la couche d'anti-corruption responsable de ce mapping : les
    couches au-dessus (workspaces, sources, jobs) ne voient jamais SecretNotFound.
    On simule le SDK via monkeypatch : harpocrate.exceptions.SecretNotFound est
    remplacé par FakeSecretNotFound, et le client vault lève cette exception.
    """
    import sys
    import types

    # Crée un module fictif harpocrate.exceptions exposant SecretNotFound.
    fake_module = types.ModuleType("harpocrate.exceptions")
    fake_module.SecretNotFound = FakeSecretNotFound  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "harpocrate.exceptions", fake_module)

    client = FakeVaultClientRaisesSecretNotFound()
    r = SecretResolver(harpocrate_clients={"myvault": client}, cache_ttl=0)

    with pytest.raises(VaultLookupFailed, match="Secret not found in vault"):
        await r.resolve("${vault://myvault:my/secret/path}")
