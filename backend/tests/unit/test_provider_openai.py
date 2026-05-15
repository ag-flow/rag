from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)


def _vec(dim: int = 1536, fill: float = 0.1) -> list[float]:
    return [fill] * dim


def _ok_response(texts: list[str]) -> httpx.Response:
    data = [{"embedding": _vec(), "index": i} for i in range(len(texts))]
    return httpx.Response(200, json={"data": data, "model": "text-embedding-3-small"})


@pytest.mark.asyncio
async def test_openai_embed_texts_success() -> None:
    captured_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.content)
        return _ok_response(captured_request["body"]["input"])

    transport = httpx.MockTransport(handler)
    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-test",
        transport=transport,
    )
    result = await provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert len(result[0]) == 1536
    assert captured_request["url"] == "https://api.openai.com/v1/embeddings"
    assert captured_request["headers"]["authorization"] == "Bearer sk-test"
    assert captured_request["body"]["model"] == "text-embedding-3-small"
    assert captured_request["body"]["input"] == ["hello", "world"]


@pytest.mark.asyncio
async def test_openai_embed_texts_auth_error_raises_typed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embed_texts_rate_limited_after_retry_raises() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(429, json={"error": {"message": "Rate limit"}})

    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingRateLimited):
        await provider.embed_texts(["hello"])
    # 1 call initial + 1 retry = 2 appels
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_openai_embed_texts_batches_over_100() -> None:
    """Si > 100 textes, OpenAIProvider doit faire 2+ calls et concat dans l'ordre."""
    batches_received: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches_received.append(len(body["input"]))
        data = [{"embedding": _vec(), "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-x",
        transport=httpx.MockTransport(handler),
    )
    texts = [f"text-{i}" for i in range(150)]
    result = await provider.embed_texts(texts)
    assert len(result) == 150
    # 2 batches : 100 + 50
    assert batches_received == [100, 50]


@pytest.mark.asyncio
async def test_openai_embed_texts_timeout_raises_unreachable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = OpenAIProvider(
        model="text-embedding-3-small",
        api_key="sk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_openai_embed_texts_missing_api_key_raises_auth() -> None:
    provider = OpenAIProvider(model="text-embedding-3-small", api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])
