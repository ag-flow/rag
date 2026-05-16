from __future__ import annotations

import pytest

from rag.secrets.resolver import SecretResolver


def test_resolver_requires_exactly_one_source() -> None:
    """Le constructeur impose XOR strict sur (harpocrate_clients, client_provider)."""
    with pytest.raises(ValueError, match="EXACTEMENT un"):
        SecretResolver()  # ni l'un ni l'autre

    with pytest.raises(ValueError, match="EXACTEMENT un"):
        SecretResolver(
            harpocrate_clients={},
            client_provider=object(),  # type: ignore[arg-type]
        )


def test_resolver_with_dict_legacy_still_works() -> None:
    """Mode legacy : `harpocrate_clients` seul → provider laissé à None."""
    r = SecretResolver(harpocrate_clients={})
    assert r._clients == {}
    assert r._provider is None


def test_resolver_with_provider_accepts_provider() -> None:
    """Mode DB-live : `client_provider` seul → clients laissé à None."""
    provider = object()  # mock minimal — pas appelé dans ce test
    r = SecretResolver(client_provider=provider)  # type: ignore[arg-type]
    assert r._provider is provider
    assert r._clients is None
