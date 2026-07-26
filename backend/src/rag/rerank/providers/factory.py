from __future__ import annotations

from rag.rerank.protocol import RerankProvider
from rag.rerank.providers.azure_foundry import AzureFoundryRerankProvider
from rag.rerank.providers.cohere import CohereRerankProvider
from rag.rerank.providers.dashscope import DashScopeRerankProvider
from rag.rerank.providers.deepinfra import DeepInfraRerankProvider
from rag.rerank.providers.fireworks import FireworksRerankProvider
from rag.rerank.providers.jina import JinaRerankProvider
from rag.rerank.providers.mixedbread import MixedbreadRerankProvider
from rag.rerank.providers.ollama import OllamaRerankProvider
from rag.rerank.providers.voyage import VoyageRerankProvider


def make_rerank_provider(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> RerankProvider:
    """Factory d'instances `RerankProvider` selon le triplet (provider, key, url)."""
    if provider == "cohere":
        if not api_key:
            raise ValueError("cohere requires api_key")
        return CohereRerankProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "voyage":
        if not api_key:
            raise ValueError("voyage requires api_key")
        return VoyageRerankProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "ollama":
        if not base_url:
            raise ValueError("ollama requires base_url")
        return OllamaRerankProvider(model=model, base_url=base_url)
    if provider == "jina":
        if not api_key:
            raise ValueError("jina requires api_key")
        return JinaRerankProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "dashscope":
        if not api_key:
            raise ValueError("dashscope requires api_key")
        return DashScopeRerankProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "fireworks":
        if not api_key:
            raise ValueError("fireworks requires api_key")
        return FireworksRerankProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "deepinfra":
        if not api_key:
            raise ValueError("deepinfra requires api_key")
        return DeepInfraRerankProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "mixedbread":
        if not api_key:
            raise ValueError("mixedbread requires api_key")
        return MixedbreadRerankProvider(model=model, api_key=api_key, base_url=base_url)
    if provider == "azure-foundry":
        if not api_key:
            raise ValueError("azure-foundry requires api_key")
        if not base_url:
            raise ValueError("azure-foundry requires base_url")
        return AzureFoundryRerankProvider(
            model=model, api_key=api_key, base_url=base_url,
        )
    raise ValueError(f"unknown rerank provider: {provider}")
