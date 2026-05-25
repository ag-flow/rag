from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.ollama import OllamaProvider


def _vec(dim: int = 768, fill: float = 0.3) -> list[float]:
    return [fill] * dim


def _resp(dim: int = 768, fill: float = 0.3) -> dict:
    """Réponse Ollama /api/embed : {"embeddings": [[...float...]]}."""
    return {"embeddings": [_vec(dim, fill)]}


@pytest.mark.asyncio
async def test_ollama_embed_texts_calls_once_per_input() -> None:
    """L'API Ollama /api/embed est mono-input : on doit boucler."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json=_resp())

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://test.local:11434",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world", "foo"])
    assert len(result) == 3
    assert len(calls) == 3
    assert calls[0]["model"] == "nomic-embed-text"
    assert calls[0]["input"] == "hello"
    assert calls[1]["input"] == "world"
    assert calls[2]["input"] == "foo"


@pytest.mark.asyncio
async def test_ollama_embed_texts_uses_base_url() -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json=_resp())

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://my-ollama.example:9999",
        transport=httpx.MockTransport(handler),
    )
    await provider.embed_texts(["hello"])
    assert captured_urls == ["http://my-ollama.example:9999/api/embed"]


@pytest.mark.asyncio
async def test_ollama_embed_empty_input_returns_empty() -> None:
    """Pas d'appel HTTP si input vide."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_resp())

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts([])
    assert result == []
    assert calls == 0


@pytest.mark.asyncio
async def test_ollama_embed_missing_embeddings_field_raises() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderError

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not_embeddings": []})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingProviderError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_ollama_embed_empty_embeddings_list_raises() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderError

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": []})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingProviderError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_ollama_embed_503_after_retry_raises_unreachable() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderUnreachable

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, json={"error": "Loading model"})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_ollama_embed_503_succeeds_on_retry() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(503, json={"error": "Loading"})
        return httpx.Response(200, json=_resp())

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    result = await provider.embed_texts(["hello"])
    assert len(result) == 1
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_ollama_embed_timeout_after_retry_raises_unreachable() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderUnreachable

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        raise httpx.TimeoutException("timeout")

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_ollama_embed_unexpected_status_raises_unreachable() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderUnreachable

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Model not found"})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
