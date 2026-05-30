from __future__ import annotations

from rag.indexer.providers.azure_openai import AzureOpenAIProvider
from rag.indexer.providers.jina import JinaProvider
from rag.indexer.providers.mistral import MistralProvider
from rag.indexer.providers.ollama import OllamaProvider
from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.indexer.providers.voyage import VoyageProvider

_OLLAMA_DEFAULT_BASE_URL = "http://192.168.10.80:11434"


def make_provider(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> EmbeddingProvider:
    """Dispatch sur le provider configuré pour un workspace.

    - `openai` / `voyage` / `mistral` / `jina` : `api_key` requis.
    - `azure-openai` : `api_key` + `base_url` requis
      (base_url = URL complète du deployment Azure).
    - `ollama` : `api_key` ignoré ; `base_url` fallback sur pve2 homelab.
    - Provider inconnu : `ValueError`.
    """
    if provider == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    if provider == "voyage":
        return VoyageProvider(model=model, api_key=api_key)
    if provider == "azure-openai":
        if not base_url:
            raise ValueError(
                "azure-openai provider requires base_url "
                "(https://{resource}.openai.azure.com/openai/deployments/{deployment_name})"
            )
        return AzureOpenAIProvider(base_url=base_url, api_key=api_key)
    if provider == "ollama":
        return OllamaProvider(
            model=model,
            base_url=base_url or _OLLAMA_DEFAULT_BASE_URL,
        )
    if provider == "mistral":
        return MistralProvider(model=model, api_key=api_key)
    if provider == "jina":
        return JinaProvider(model=model, api_key=api_key)
    raise ValueError(f"Unsupported provider: {provider!r}")
