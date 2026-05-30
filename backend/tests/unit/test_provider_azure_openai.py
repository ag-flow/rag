from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.azure_openai import AzureOpenAIProvider
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)

_BASE_URL = "https://myresource.openai.azure.com/openai/deployments/text-embedding-3-small"
_API_VERSION = "2024-02-01"


def _vec(dim: int = 1536, fill: float = 0.1) -> list[float]:
    return [fill] * dim


def _ok_response(texts: list[str]) -> httpx.Response:
    data = [{"embedding": _vec(), "index": i} for i in range(len(texts))]
    return httpx.Response(200, json={"data": data})


@pytest.mark.asyncio
async def test_azure_embed_texts_success() -> None:
    """Verifie l'URL, le header api-key, l'absence de champ model dans le body."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return _ok_response(captured["body"]["input"])

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-test-key",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world"])

    assert len(result) == 2
    assert len(result[0]) == 1536
    assert captured["url"] == f"{_BASE_URL}/embeddings?api-version={_API_VERSION}"
    assert captured["headers"]["api-key"] == "az-test-key"
    assert "authorization" not in captured["headers"]
    assert captured["body"]["input"] == ["hello", "world"]
    assert "model" not in captured["body"]


@pytest.mark.asyncio
async def test_azure_embed_texts_missing_api_key_raises_auth() -> None:
    provider = AzureOpenAIProvider(base_url=_BASE_URL, api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_azure_embed_empty_input_returns_empty() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts([])
    assert result == []
    assert calls == 0


@pytest.mark.asyncio
async def test_azure_embed_texts_401_raises_auth_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Unauthorized"}})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_azure_embed_texts_rate_limited_after_retry_raises() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(429, json={"error": {"message": "Rate limit"}})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingRateLimited):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_azure_embed_texts_503_after_retry_raises_unreachable() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, json={"error": "Down"})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_azure_embed_texts_timeout_raises_unreachable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_azure_embed_texts_batches_over_100() -> None:
    batches_received: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches_received.append(len(body["input"]))
        data = [{"embedding": _vec(), "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
    )
    texts = [f"text-{i}" for i in range(150)]
    result = await provider.embed_texts(texts)
    assert len(result) == 150
    assert batches_received == [100, 50]


@pytest.mark.asyncio
async def test_azure_embed_query_returns_single_vector() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        data = [{"embedding": _vec(), "index": 0}]
        return httpx.Response(200, json={"data": data})

    provider = AzureOpenAIProvider(
        base_url=_BASE_URL,
        api_key="az-key",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_query("ma requete")
    assert len(result) == 1536
