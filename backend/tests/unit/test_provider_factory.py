from __future__ import annotations

import pytest

from rag.indexer.providers.azure_openai import AzureOpenAIProvider
from rag.indexer.providers.factory import make_provider
from rag.indexer.providers.ollama import OllamaProvider
from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.voyage import VoyageProvider


def test_make_provider_openai_returns_openai_instance() -> None:
    p = make_provider(
        provider="openai",
        model="text-embedding-3-small",
        api_key="sk-x",
        base_url=None,
    )
    assert isinstance(p, OpenAIProvider)


def test_make_provider_voyage_returns_voyage_instance() -> None:
    p = make_provider(
        provider="voyage",
        model="voyage-3",
        api_key="vk-x",
        base_url=None,
    )
    assert isinstance(p, VoyageProvider)


def test_make_provider_ollama_uses_default_base_url() -> None:
    p = make_provider(
        provider="ollama",
        model="nomic-embed-text",
        api_key=None,
        base_url=None,
    )
    assert isinstance(p, OllamaProvider)


def test_make_provider_ollama_uses_explicit_base_url() -> None:
    p = make_provider(
        provider="ollama",
        model="nomic-embed-text",
        api_key=None,
        base_url="http://custom-ollama:11434",
    )
    assert isinstance(p, OllamaProvider)


def test_make_provider_unknown_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        make_provider(
            provider="cohere",
            model="x",
            api_key=None,
            base_url=None,
        )


def test_make_provider_azure_openai_returns_azure_instance() -> None:
    p = make_provider(
        provider="azure-openai",
        model="text-embedding-3-small",
        api_key="az-key",
        base_url="https://myresource.openai.azure.com/openai/deployments/text-embedding-3-small",
    )
    assert isinstance(p, AzureOpenAIProvider)


def test_make_provider_azure_openai_without_base_url_raises() -> None:
    with pytest.raises(ValueError, match="base_url"):
        make_provider(
            provider="azure-openai",
            model="text-embedding-3-small",
            api_key="az-key",
            base_url=None,
        )
