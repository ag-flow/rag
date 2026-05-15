from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.ollama import OllamaProvider


def _vec(dim: int = 768, fill: float = 0.3) -> list[float]:
    return [fill] * dim


@pytest.mark.asyncio
async def test_ollama_embed_texts_calls_once_per_input() -> None:
    """L'API Ollama /api/embeddings est mono-input : on doit boucler."""
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"embedding": _vec()})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://test.local:11434",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world", "foo"])
    assert len(result) == 3
    assert len(calls) == 3
    assert calls[0]["model"] == "nomic-embed-text"
    assert calls[0]["prompt"] == "hello"
    assert calls[1]["prompt"] == "world"
    assert calls[2]["prompt"] == "foo"


@pytest.mark.asyncio
async def test_ollama_embed_texts_uses_base_url() -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={"embedding": _vec()})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://my-ollama.example:9999",
        transport=httpx.MockTransport(handler),
    )
    await provider.embed_texts(["hello"])
    assert captured_urls == ["http://my-ollama.example:9999/api/embeddings"]


@pytest.mark.asyncio
async def test_ollama_embed_empty_input_returns_empty() -> None:
    """Pas d'appel HTTP si input vide."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"embedding": _vec()})

    provider = OllamaProvider(
        model="nomic-embed-text",
        base_url="http://x:1",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts([])
    assert result == []
    assert calls == 0
