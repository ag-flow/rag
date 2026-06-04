# backend/src/rag/indexer/providers/factory.py
from __future__ import annotations

from rag.indexer.providers.adapter import EmbeddingProviderAdapter
from rag.indexer.providers.platforms.azure_openai import AzureOpenAIPlatform
from rag.indexer.providers.platforms.bearer import BearerPlatform
from rag.indexer.providers.platforms.ollama import OllamaPlatform
from rag.indexer.providers.protocol import EmbeddingProvider
from rag.indexer.providers.services.dashscope import DashScopeService
from rag.indexer.providers.services.jina import JinaService
from rag.indexer.providers.services.ollama import OllamaService
from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService
from rag.indexer.providers.services.voyage import VoyageService

_DIRECT_URLS: dict[str, str] = {
    "openai":    "https://api.openai.com/v1",
    "voyage":    "https://api.voyageai.com/v1",
    "mistral":   "https://api.mistral.ai/v1",
    "jina":      "https://api.jina.ai/v1",
    "gemini":    "https://generativelanguage.googleapis.com/v1beta/openai",
    "dashscope": "https://dashscope-intl.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
}

_OLLAMA_DEFAULT_BASE_URL = "http://192.168.10.80:11434"


def make_provider(
    *,
    service: str,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> EmbeddingProvider:
    """Construit un EmbeddingProvider à partir du service + provider configurés.

    service  : capacité IA (openai, voyage, jina, dashscope, ollama, mistral, gemini).
               Disponible dans model_dimensions.service.
    provider : plateforme d'accès (openai, voyage, mistral, jina, gemini,
               dashscope, ollama, azure-openai, azure-foundry).
    """
    svc = _make_service(service)
    plat = _make_platform(provider, api_key=api_key, base_url=base_url)
    return EmbeddingProviderAdapter(service=svc, platform=plat, model=model)


def _make_service(service: str):
    if service in ("openai", "mistral", "gemini"):
        return OpenAICompatibleService()
    if service == "voyage":
        return VoyageService()
    if service == "jina":
        return JinaService()
    if service == "dashscope":
        return DashScopeService()
    if service == "ollama":
        return OllamaService()
    raise ValueError(f"Unsupported service: {service!r}")


def _make_platform(provider: str, *, api_key: str | None, base_url: str | None):
    if provider == "azure-openai":
        if not base_url:
            raise ValueError(
                "azure-openai provider requires base_url "
                "(https://{resource}.openai.azure.com/openai/deployments/{deployment_name})"
            )
        return AzureOpenAIPlatform(base_url, api_key)
    if provider == "azure-foundry":
        if not base_url:
            raise ValueError(
                "azure-foundry provider requires base_url "
                "(https://{name}.{region}.models.ai.azure.com/v1)"
            )
        return BearerPlatform(base_url, api_key)
    if provider == "ollama":
        return OllamaPlatform(base_url or _OLLAMA_DEFAULT_BASE_URL)
    if provider in _DIRECT_URLS:
        return BearerPlatform(_DIRECT_URLS[provider], api_key)
    raise ValueError(f"Unsupported provider: {provider!r}")
