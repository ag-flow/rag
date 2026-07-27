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
from rag.services.provider_urls import resolve_url

_DIRECT_URLS: dict[str, str] = {
    "openai":    "https://api.openai.com/v1",
    "voyage":    "https://api.voyageai.com/v1",
    "mistral":   "https://api.mistral.ai/v1",
    "jina":      "https://api.jina.ai/v1",
    "gemini":    "https://generativelanguage.googleapis.com/v1beta/openai",
    "dashscope": "https://dashscope-intl.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
    # Plateformes cloud OpenAI-compatibles (service 'openai', auth Bearer).
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "together":  "https://api.together.xyz/v1",
    "cohere":    "https://api.cohere.ai/compatibility/v1",
}

_OLLAMA_DEFAULT_BASE_URL = "http://192.168.10.80:11434"


def make_provider(
    *,
    service: str,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    url_template: str | None = None,
) -> EmbeddingProvider:
    """Construit un EmbeddingProvider à partir du service + provider configurés.

    service      : capacité IA (openai, voyage, jina, dashscope, ollama, mistral,
                   gemini). Disponible dans model_dimensions.service.
    provider     : plateforme d'accès (openai, voyage, mistral, jina, gemini,
                   dashscope, ollama, azure-openai, azure-foundry, plateformes
                   cloud OpenAI-compatibles).
    url_template : surcharge d'URL portée par le modèle du registre
                   (model_dimensions.url_template) — résolue en URL complète
                   qui court-circuite la construction plateforme+service.
    """
    svc = _make_service(service)
    plat = _make_platform(provider, api_key=api_key, base_url=base_url, model=model)
    url_override = resolve_url(
        provider=provider,
        capability="embeddings",
        model=model,
        base_url=base_url,
        template=url_template,
    ) if url_template else None
    return EmbeddingProviderAdapter(
        service=svc, platform=plat, model=model, url_override=url_override
    )


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


def _make_platform(
    provider: str, *, api_key: str | None, base_url: str | None, model: str = ""
):
    if provider == "azure-openai":
        if not base_url:
            raise ValueError(
                "azure-openai provider requires base_url "
                "(https://{resource}.openai.azure.com — racine de la ressource)"
            )
        # Racine de ressource acceptée : le chemin de déploiement est dérivé du
        # modèle. Une base_url legacy contenant déjà /openai/deployments/ passe
        # inchangée (compat).
        if "/openai/deployments/" not in base_url:
            base_url = f"{base_url.rstrip('/')}/openai/deployments/{model}"
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
