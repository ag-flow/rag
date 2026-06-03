from __future__ import annotations

import json as _json

import httpx
import pytest

from rag.indexer.providers.dashscope import DashScopeEmbeddingProvider, _URL_INTERNATIONAL
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)


def _ok_transport(vectors: list[list[float]]) -> httpx.MockTransport:
    payload = {
        "output": {
            "embeddings": [{"text_index": i, "embedding": v} for i, v in enumerate(vectors)]
        }
    }

    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def _status_transport(status: int) -> httpx.MockTransport:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_embed_texts_returns_one_vector_per_text() -> None:
    vecs = [[0.1, 0.2], [0.3, 0.4]]
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk", transport=_ok_transport(vecs)
    )
    result = await provider.embed_texts(["a", "b"])
    assert result == vecs


@pytest.mark.asyncio
async def test_embed_texts_preserves_order_when_api_returns_shuffled() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "output": {
                "embeddings": [
                    {"text_index": 1, "embedding": [0.3, 0.4]},
                    {"text_index": 0, "embedding": [0.1, 0.2]},
                ]
            }
        })

    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk", transport=httpx.MockTransport(handler)
    )
    result = await provider.embed_texts(["a", "b"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.asyncio
async def test_embed_texts_empty_returns_empty() -> None:
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk", transport=_ok_transport([])
    )
    assert await provider.embed_texts([]) == []


@pytest.mark.asyncio
async def test_embed_texts_batches_over_25() -> None:
    calls: list[list[str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = _json.loads(req.content)
        texts = body["input"]["texts"]
        calls.append(texts)
        return httpx.Response(200, json={
            "output": {
                "embeddings": [
                    {"text_index": i, "embedding": [float(i)]} for i in range(len(texts))
                ]
            }
        })

    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk", transport=httpx.MockTransport(handler)
    )
    texts = [str(i) for i in range(60)]
    result = await provider.embed_texts(texts)
    assert len(calls) == 3
    assert len(calls[0]) == 25
    assert len(calls[1]) == 25
    assert len(calls[2]) == 10
    assert len(result) == 60


@pytest.mark.asyncio
async def test_embed_query_returns_single_vector() -> None:
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk", transport=_ok_transport([[0.9, 0.8]])
    )
    vec = await provider.embed_query("ma question")
    assert vec == [0.9, 0.8]


@pytest.mark.asyncio
async def test_hits_international_endpoint_by_default() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["auth"] = req.headers.get("authorization")
        captured["body"] = _json.loads(req.content)
        return httpx.Response(200, json={
            "output": {"embeddings": [{"text_index": 0, "embedding": [0.1]}]}
        })

    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="my-key", transport=httpx.MockTransport(handler)
    )
    await provider.embed_texts(["hello"])
    assert captured["url"] == _URL_INTERNATIONAL
    assert captured["auth"] == "Bearer my-key"
    assert captured["body"]["input"]["texts"] == ["hello"]
    assert captured["body"]["model"] == "text-embedding-v4"


@pytest.mark.asyncio
async def test_custom_base_url_overrides_default() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json={
            "output": {"embeddings": [{"text_index": 0, "embedding": [0.1]}]}
        })

    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4",
        api_key="sk",
        base_url="https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
        transport=httpx.MockTransport(handler),
    )
    await provider.embed_texts(["hello"])
    assert "dashscope.aliyuncs.com" in captured["url"]


@pytest.mark.asyncio
async def test_api_key_none_raises_auth_error() -> None:
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key=None, transport=_ok_transport([])
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["x"])


@pytest.mark.asyncio
async def test_http_401_raises_auth_error() -> None:
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk", transport=_status_transport(401)
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["x"])


@pytest.mark.asyncio
async def test_http_403_raises_auth_error() -> None:
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk", transport=_status_transport(403)
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["x"])


@pytest.mark.asyncio
async def test_http_429_retries_then_raises_rate_limited() -> None:
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk",
        transport=_status_transport(429),
        retry_sleep_seconds=0.0,
    )
    with pytest.raises(EmbeddingRateLimited):
        await provider.embed_texts(["x"])


@pytest.mark.asyncio
async def test_http_503_retries_then_raises_unreachable() -> None:
    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk",
        transport=_status_transport(503),
        retry_sleep_seconds=0.0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["x"])


@pytest.mark.asyncio
async def test_timeout_retries_then_raises_unreachable() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0.0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["x"])


@pytest.mark.asyncio
async def test_429_first_attempt_then_success_returns_vectors() -> None:
    attempt = 0

    def handler(_req: httpx.Request) -> httpx.Response:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={
            "output": {"embeddings": [{"text_index": 0, "embedding": [1.0]}]}
        })

    provider = DashScopeEmbeddingProvider(
        model="text-embedding-v4", api_key="sk",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0.0,
    )
    result = await provider.embed_texts(["x"])
    assert result == [[1.0]]
    assert attempt == 2
