# backend/tests/unit/test_adapter.py
from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.adapter import EmbeddingProviderAdapter
from rag.indexer.providers.platforms.bearer import BearerPlatform
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)
from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService
from rag.indexer.providers.services.voyage import VoyageService

_BASE = "https://api.example.com/v1"
_KEY = "test-key"


def _make_adapter(*, service=None, platform=None, model="test-model", transport=None, retry_sleep=0.0):
    svc = service or OpenAICompatibleService()
    plat = platform or BearerPlatform(_BASE, _KEY)
    return EmbeddingProviderAdapter(
        service=svc,
        platform=plat,
        model=model,
        transport=transport,
        retry_sleep_seconds=retry_sleep,
    )


def _ok_response(texts: list[str], dim: int = 4) -> httpx.Response:
    data = [{"embedding": [0.1] * dim, "index": i} for i in range(len(texts))]
    return httpx.Response(200, json={"data": data})


@pytest.mark.asyncio
async def test_embed_texts_empty_returns_empty() -> None:
    adapter = _make_adapter()
    result = await adapter.embed_texts([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_texts_success_url_headers_body() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return _ok_response(captured["body"]["input"])

    adapter = _make_adapter(transport=httpx.MockTransport(handler))
    result = await adapter.embed_texts(["hello", "world"])

    assert len(result) == 2
    assert len(result[0]) == 4
    assert captured["url"] == f"{_BASE}/embeddings"
    assert captured["headers"]["authorization"] == f"Bearer {_KEY}"
    assert captured["body"] == {"model": "test-model", "input": ["hello", "world"]}


@pytest.mark.asyncio
async def test_embed_texts_batches_at_service_batch_size() -> None:
    batches: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches.append(len(body["input"]))
        data = [{"embedding": [0.1], "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    adapter = _make_adapter(transport=httpx.MockTransport(handler))
    # OpenAICompatibleService.batch_size = 100
    texts = [f"t{i}" for i in range(150)]
    result = await adapter.embed_texts(texts)
    assert len(result) == 150
    assert batches == [100, 50]


@pytest.mark.asyncio
async def test_embed_texts_no_api_key_raises_auth_error() -> None:
    adapter = _make_adapter(platform=BearerPlatform(_BASE, None))
    with pytest.raises(EmbeddingAuthError):
        await adapter.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_embed_texts_401_raises_auth_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    adapter = _make_adapter(transport=httpx.MockTransport(handler))
    with pytest.raises(EmbeddingAuthError):
        await adapter.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_embed_texts_429_retries_once_then_raises_rate_limited() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={"error": "Rate limit"})

    adapter = _make_adapter(transport=httpx.MockTransport(handler), retry_sleep=0.0)
    with pytest.raises(EmbeddingRateLimited):
        await adapter.embed_texts(["hello"])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_embed_texts_503_retries_once_then_raises_unreachable() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "Down"})

    adapter = _make_adapter(transport=httpx.MockTransport(handler), retry_sleep=0.0)
    with pytest.raises(EmbeddingProviderUnreachable):
        await adapter.embed_texts(["hello"])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_embed_texts_timeout_retries_once_then_raises_unreachable() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.TimeoutException("timeout")

    adapter = _make_adapter(transport=httpx.MockTransport(handler), retry_sleep=0.0)
    with pytest.raises(EmbeddingProviderUnreachable):
        await adapter.embed_texts(["hello"])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_embed_query_uses_build_query_payload() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2], "index": 0}]})

    adapter = _make_adapter(
        service=VoyageService(),
        transport=httpx.MockTransport(handler),
        model="voyage-4",
    )
    result = await adapter.embed_query("ma requête")
    assert result == [0.1, 0.2]
    assert captured["body"]["input_type"] == "query"
    assert captured["body"]["input"] == ["ma requête"]


@pytest.mark.asyncio
async def test_azure_openai_platform_strips_model_from_payload() -> None:
    from rag.indexer.providers.platforms.azure_openai import AzureOpenAIPlatform

    captured: dict = {}
    _AZ_BASE = "https://res.openai.azure.com/openai/deployments/emb"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        body = json.loads(request.content)
        data = [{"embedding": [0.1], "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    adapter = EmbeddingProviderAdapter(
        service=OpenAICompatibleService(),
        platform=AzureOpenAIPlatform(_AZ_BASE, "az-key"),
        model="text-embedding-3-small",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0.0,
    )
    await adapter.embed_texts(["hello"])

    assert "model" not in captured["body"]
    assert captured["headers"]["api-key"] == "az-key"
    assert "api-version=2024-02-01" in captured["url"]
