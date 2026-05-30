from __future__ import annotations

from rag.rerank.protocol import RerankProvider
from rag.rerank.providers.cohere import CohereRerankProvider
from rag.rerank.providers.jina import JinaRerankProvider
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
        return CohereRerankProvider(model=model, api_key=api_key)
    if provider == "voyage":
        if not api_key:
            raise ValueError("voyage requires api_key")
        return VoyageRerankProvider(model=model, api_key=api_key)
    if provider == "ollama":
        if not base_url:
            raise ValueError("ollama requires base_url")
        return OllamaRerankProvider(model=model, base_url=base_url)
    if provider == "jina":
        if not api_key:
            raise ValueError("jina requires api_key")
        return JinaRerankProvider(model=model, api_key=api_key)
    raise ValueError(f"unknown rerank provider: {provider}")
