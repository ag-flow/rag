from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.mistral import MistralProvider
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)


def _vec(dim: int = 1024, fill: float = 0.1) -> list[float]:
    return [fill] * dim


@pytest.mark.asyncio
async def test_mistral_embed_texts_success() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        data = [{"embedding": _vec(), "index": i} for i in range(len(captured["body"]["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert len(result[0]) == 1024
    assert captured["body"]["model"] == "mistral-embed"
    assert captured["body"]["input"] == ["hello", "world"]


@pytest.mark.asyncio
async def test_mistral_embed_texts_empty_returns_empty() -> None:
    """Pas d'appel HTTP si input vide."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts([])
    assert result == []
    assert calls == 0


@pytest.mark.asyncio
async def test_mistral_embed_texts_missing_api_key_raises() -> None:
    provider = MistralProvider(model="mistral-embed", api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_mistral_embed_query_missing_api_key_raises() -> None:
    provider = MistralProvider(model="mistral-embed", api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_query("hello")


@pytest.mark.asyncio
async def test_mistral_embed_query_success() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        data = [{"embedding": _vec(), "index": 0}]
        return httpx.Response(200, json={"data": data})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_query("ma requete")
    assert len(result) == 1024


@pytest.mark.asyncio
async def test_mistral_embed_texts_auth_error_401() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_mistral_embed_texts_auth_error_403() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Forbidden"})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_mistral_embed_texts_rate_limited_after_retry() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(429, json={"error": "Rate limited"})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingRateLimited):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_mistral_embed_texts_429_succeeds_on_retry() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, json={"error": "Rate limited"})
        data = [{"embedding": _vec(), "index": 0}]
        return httpx.Response(200, json={"data": data})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    result = await provider.embed_texts(["hello"])
    assert len(result) == 1
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_mistral_embed_texts_503_after_retry_raises_unreachable() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, json={"error": "Service unavailable"})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_mistral_embed_texts_timeout_after_retry_raises_unreachable() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        raise httpx.TimeoutException("timeout")

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_mistral_embed_texts_unexpected_status_raises_unreachable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, json={"error": "I'm a teapot"})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-x",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_mistral_embed_texts_batches_over_100() -> None:
    """Si > 100 textes, MistralProvider doit faire 2+ appels et concatener dans l'ordre."""
    batches_received: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches_received.append(len(body["input"]))
        data = [{"embedding": _vec(), "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-x",
        transport=httpx.MockTransport(handler),
    )
    texts = [f"text-{i}" for i in range(150)]
    result = await provider.embed_texts(texts)
    assert len(result) == 150
    # 2 batches : 100 + 50
    assert batches_received == [100, 50]


@pytest.mark.asyncio
async def test_mistral_embed_texts_response_sorted_by_index() -> None:
    """Les embeddings sont tries par index meme si l'API les renvoie dans le desordre."""

    def handler(_request: httpx.Request) -> httpx.Response:
        data = [
            {"embedding": [0.9, 0.9], "index": 1},
            {"embedding": [0.1, 0.1], "index": 0},
        ]
        return httpx.Response(200, json={"data": data})

    provider = MistralProvider(
        model="mistral-embed",
        api_key="mk-x",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["a", "b"])
    assert result[0] == [0.1, 0.1]
    assert result[1] == [0.9, 0.9]
