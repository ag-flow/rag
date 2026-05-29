from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.jina import JinaRerankProvider


def _mock_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_jina_returns_sorted_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.jina.ai"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.99},
                    {"index": 0, "relevance_score": 0.50},
                    {"index": 1, "relevance_score": 0.10},
                ],
            },
        )

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="test-key",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=3)
    assert indices == [2, 0, 1]


@pytest.mark.asyncio
async def test_jina_empty_documents() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        pytest.fail("should not call api for empty documents")

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="test-key",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=[], top_k=5)
    assert indices == []


@pytest.mark.asyncio
async def test_jina_respects_top_n() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content
        assert b'"top_n":2' in body or b'"top_n": 2' in body
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.99},
                    {"index": 0, "relevance_score": 0.50},
                ],
            },
        )

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="test-key",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=2)
    assert indices == [1, 0]


@pytest.mark.asyncio
async def test_jina_auth_error_on_401() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="bad",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_jina_auth_error_on_403() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_jina_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_jina_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_jina_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_jina_unreachable_on_network_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.RequestError("network error")

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_jina_unreachable_on_unexpected_4xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")

    provider = JinaRerankProvider(
        model="jina-reranker-v2-base-multilingual",
        api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
