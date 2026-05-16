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
