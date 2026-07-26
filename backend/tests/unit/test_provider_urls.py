from __future__ import annotations

from rag.services.provider_urls import PROVIDER_URL_TEMPLATES, resolve_url


def test_azure_openai_embeddings_from_resource_root() -> None:
    url = resolve_url(
        provider="azure-openai",
        capability="embeddings",
        model="text-embedding-3-large",
        base_url="https://rag-agflow.openai.azure.com",
    )
    assert url == (
        "https://rag-agflow.openai.azure.com/openai/deployments/"
        "text-embedding-3-large/embeddings?api-version=2024-02-01"
    )


def test_default_base_url_applies_when_absent() -> None:
    assert (
        resolve_url(provider="openai", capability="embeddings", model="m")
        == "https://api.openai.com/v1/embeddings"
    )
    assert (
        resolve_url(provider="deepinfra", capability="rerank", model="Qwen/Qwen3-Reranker-4B")
        == "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-4B"
    )


def test_model_template_override_wins_and_accepts_url_alias() -> None:
    url = resolve_url(
        provider="azure-openai",
        capability="embeddings",
        model="text-embedding-3-large",
        base_url="https://x.openai.azure.com",
        template="{url}/openai/deployments/mon-deploiement/embeddings?api-version=2024-02-01",
    )
    assert url == (
        "https://x.openai.azure.com/openai/deployments/"
        "mon-deploiement/embeddings?api-version=2024-02-01"
    )


def test_unknown_capability_or_missing_required_base_returns_none() -> None:
    assert resolve_url(provider="bedrock", capability="embeddings", model="m") is None
    assert resolve_url(provider="openai", capability="rerank", model="m") is None
    # azure-openai exige une base : pas de défaut.
    assert resolve_url(provider="azure-openai", capability="embeddings", model="m") is None


def test_referential_covers_wired_llm_and_rerank_providers() -> None:
    """Chaque provider routé par le code a son masque (anti-dérive)."""
    for p in ("claude", "openai", "azure-openai", "ollama", "ollama-cloud",
              "gemini", "deepseek", "dashscope"):
        assert "chat" in PROVIDER_URL_TEMPLATES[p], p
    for p in ("cohere", "voyage", "ollama", "jina", "dashscope", "azure-foundry",
              "fireworks", "deepinfra", "mixedbread"):
        assert "rerank" in PROVIDER_URL_TEMPLATES[p], p
