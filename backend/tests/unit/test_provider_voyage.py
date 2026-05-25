from __future__ import annotations

import json

import httpx
import pytest

from rag.indexer.providers.protocol import EmbeddingAuthError
from rag.indexer.providers.voyage import VoyageProvider


def _vec(dim: int = 1024, fill: float = 0.2) -> list[float]:
    return [fill] * dim


@pytest.mark.asyncio
async def test_voyage_embed_texts_success_uses_input_type_document() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        data = [{"embedding": _vec(), "index": i} for i in range(len(captured["body"]["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert len(result[0]) == 1024
    # Le body doit inclure input_type=document
    assert captured["body"]["input_type"] == "document"
    assert captured["body"]["model"] == "voyage-3"


@pytest.mark.asyncio
async def test_voyage_embed_texts_missing_api_key_raises() -> None:
    provider = VoyageProvider(model="voyage-3", api_key=None)
    with pytest.raises(EmbeddingAuthError):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_voyage_embed_empty_input_returns_empty() -> None:
    """Pas d'appel HTTP si input vide."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": []})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-test",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.embed_texts([])
    assert result == []
    assert calls == 0


@pytest.mark.asyncio
async def test_voyage_embed_texts_auth_error_raises_typed() -> None:
    from rag.indexer.providers.protocol import EmbeddingAuthError as _AuthErr

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Invalid"})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(_AuthErr):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_voyage_embed_texts_forbidden_raises_auth() -> None:
    from rag.indexer.providers.protocol import EmbeddingAuthError as _AuthErr

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Forbidden"})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-bad",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(_AuthErr):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_voyage_embed_texts_rate_limited_after_retry_raises() -> None:
    from rag.indexer.providers.protocol import EmbeddingRateLimited

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(429, json={"error": "Rate"})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingRateLimited):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_voyage_embed_texts_503_after_retry_raises_unreachable() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderUnreachable

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, json={"error": "Down"})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_voyage_embed_texts_429_succeeds_on_retry() -> None:
    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, json={"error": "Rate"})
        data = [{"embedding": _vec(), "index": 0}]
        return httpx.Response(200, json={"data": data})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    result = await provider.embed_texts(["hello"])
    assert len(result) == 1
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_voyage_embed_texts_timeout_after_retry_raises_unreachable() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderUnreachable

    call_count = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        raise httpx.TimeoutException("timeout")

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-x",
        transport=httpx.MockTransport(handler),
        retry_sleep_seconds=0,
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_voyage_embed_texts_unexpected_status_raises_unreachable() -> None:
    from rag.indexer.providers.protocol import EmbeddingProviderUnreachable

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, json={"error": "Teapot"})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-x",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingProviderUnreachable):
        await provider.embed_texts(["hello"])


@pytest.mark.asyncio
async def test_voyage_embed_texts_batches_over_128() -> None:
    """Si > 128 textes, VoyageProvider doit faire 2+ calls et concat dans l'ordre."""
    batches_received: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batches_received.append(len(body["input"]))
        data = [{"embedding": _vec(), "index": i} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data})

    provider = VoyageProvider(
        model="voyage-3",
        api_key="vk-x",
        transport=httpx.MockTransport(handler),
    )
    texts = [f"text-{i}" for i in range(200)]
    result = await provider.embed_texts(texts)
    assert len(result) == 200
    # 2 batches : 128 + 72
    assert batches_received == [128, 72]
