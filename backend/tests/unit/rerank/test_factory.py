from __future__ import annotations

import pytest

from rag.rerank.providers.azure_foundry import AzureFoundryRerankProvider
from rag.rerank.providers.cohere import CohereRerankProvider
from rag.rerank.providers.deepinfra import DeepInfraRerankProvider
from rag.rerank.providers.factory import make_rerank_provider
from rag.rerank.providers.fireworks import FireworksRerankProvider
from rag.rerank.providers.jina import JinaRerankProvider
from rag.rerank.providers.mixedbread import MixedbreadRerankProvider
from rag.rerank.providers.ollama import OllamaRerankProvider
from rag.rerank.providers.voyage import VoyageRerankProvider


def test_factory_cohere() -> None:
    p = make_rerank_provider(
        provider="cohere", model="rerank-v3.5", api_key="k", base_url=None,
    )
    assert isinstance(p, CohereRerankProvider)


def test_factory_voyage() -> None:
    p = make_rerank_provider(
        provider="voyage", model="rerank-2", api_key="k", base_url=None,
    )
    assert isinstance(p, VoyageRerankProvider)


def test_factory_ollama() -> None:
    p = make_rerank_provider(
        provider="ollama", model="bge", api_key=None,
        base_url="http://localhost:11434",
    )
    assert isinstance(p, OllamaRerankProvider)


def test_factory_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown rerank provider"):
        make_rerank_provider(
            provider="nope", model="m", api_key="k", base_url=None,
        )


def test_factory_cohere_missing_api_key() -> None:
    with pytest.raises(ValueError, match="cohere requires api_key"):
        make_rerank_provider(
            provider="cohere", model="m", api_key=None, base_url=None,
        )


def test_factory_voyage_missing_api_key() -> None:
    with pytest.raises(ValueError, match="voyage requires api_key"):
        make_rerank_provider(
            provider="voyage", model="m", api_key=None, base_url=None,
        )


def test_factory_ollama_missing_base_url() -> None:
    with pytest.raises(ValueError, match="ollama requires base_url"):
        make_rerank_provider(
            provider="ollama", model="m", api_key=None, base_url=None,
        )


def test_factory_jina() -> None:
    p = make_rerank_provider(
        provider="jina", model="jina-reranker-v2-base-multilingual", api_key="k",
        base_url=None,
    )
    assert isinstance(p, JinaRerankProvider)


def test_factory_jina_missing_api_key() -> None:
    with pytest.raises(ValueError, match="jina requires api_key"):
        make_rerank_provider(
            provider="jina", model="m", api_key=None, base_url=None,
        )


def test_factory_azure_foundry() -> None:
    p = make_rerank_provider(
        provider="azure-foundry", model="rerank-v3.5", api_key="k",
        base_url="https://proj.services.ai.azure.com/providers/cohere/v2/rerank",
    )
    assert isinstance(p, AzureFoundryRerankProvider)


def test_factory_azure_foundry_missing_api_key() -> None:
    with pytest.raises(ValueError, match="azure-foundry requires api_key"):
        make_rerank_provider(
            provider="azure-foundry", model="m", api_key=None,
            base_url="https://x/rerank",
        )


def test_factory_azure_foundry_missing_base_url() -> None:
    with pytest.raises(ValueError, match="azure-foundry requires base_url"):
        make_rerank_provider(
            provider="azure-foundry", model="m", api_key="k", base_url=None,
        )


def test_factory_cloud_platforms() -> None:
    cases = [
        ("fireworks", FireworksRerankProvider),
        ("deepinfra", DeepInfraRerankProvider),
        ("mixedbread", MixedbreadRerankProvider),
    ]
    for provider, cls in cases:
        p = make_rerank_provider(provider=provider, model="m", api_key="k", base_url=None)
        assert isinstance(p, cls)


def test_factory_cloud_platforms_require_api_key() -> None:
    for provider in ("fireworks", "deepinfra", "mixedbread"):
        with pytest.raises(ValueError, match="requires api_key"):
            make_rerank_provider(provider=provider, model="m", api_key=None, base_url=None)
