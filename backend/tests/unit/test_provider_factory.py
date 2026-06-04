# backend/tests/unit/test_provider_factory.py
from __future__ import annotations

import pytest

from rag.indexer.providers.adapter import EmbeddingProviderAdapter
from rag.indexer.providers.factory import make_provider


def _make(**kwargs):
    defaults = dict(service="openai", provider="openai", model="text-embedding-3-small",
                    api_key="sk-x", base_url=None)
    defaults.update(kwargs)
    return make_provider(**defaults)


def test_openai_direct_returns_adapter() -> None:
    p = _make(service="openai", provider="openai")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_voyage_direct_returns_adapter() -> None:
    p = _make(service="voyage", provider="voyage", model="voyage-3", api_key="vk-x")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_mistral_returns_adapter() -> None:
    p = _make(service="mistral", provider="mistral", model="mistral-embed")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_jina_returns_adapter() -> None:
    p = _make(service="jina", provider="jina", model="jina-embeddings-v3")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_gemini_returns_adapter() -> None:
    p = _make(service="gemini", provider="gemini", model="gemini-embedding-001")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_dashscope_returns_adapter() -> None:
    p = _make(service="dashscope", provider="dashscope", model="text-embedding-v3")
    assert isinstance(p, EmbeddingProviderAdapter)


def test_ollama_returns_adapter() -> None:
    p = _make(service="ollama", provider="ollama", model="nomic-embed-text", api_key=None)
    assert isinstance(p, EmbeddingProviderAdapter)


def test_ollama_no_base_url_uses_default() -> None:
    p = _make(service="ollama", provider="ollama", model="nomic-embed-text", api_key=None)
    assert isinstance(p, EmbeddingProviderAdapter)


def test_azure_openai_returns_adapter() -> None:
    p = _make(
        service="openai", provider="azure-openai",
        base_url="https://res.openai.azure.com/openai/deployments/emb",
    )
    assert isinstance(p, EmbeddingProviderAdapter)


def test_azure_openai_without_base_url_raises() -> None:
    with pytest.raises(ValueError, match="base_url"):
        _make(service="openai", provider="azure-openai", base_url=None)


def test_azure_foundry_voyage_returns_adapter() -> None:
    p = _make(
        service="voyage", provider="azure-foundry",
        model="voyage-4",
        base_url="https://name.region.models.ai.azure.com/v1",
    )
    assert isinstance(p, EmbeddingProviderAdapter)


def test_azure_foundry_without_base_url_raises() -> None:
    with pytest.raises(ValueError, match="base_url"):
        _make(service="voyage", provider="azure-foundry", base_url=None)


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        _make(provider="cohere")


def test_unknown_service_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported service"):
        _make(service="unknown-svc")
