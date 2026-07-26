from __future__ import annotations

from rag.services.models import service_for_provider


def test_service_for_provider_known_platforms() -> None:
    assert service_for_provider("ollama") == "ollama"
    assert service_for_provider("ollama-cloud") == "ollama"
    assert service_for_provider("voyage") == "voyage"
    assert service_for_provider("bedrock") == "bedrock"


def test_service_for_provider_defaults_to_openai_compatible() -> None:
    for provider in ("fireworks", "deepinfra", "together", "cohere", "azure-openai"):
        assert service_for_provider(provider) == "openai"
