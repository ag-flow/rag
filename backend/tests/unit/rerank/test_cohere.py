from __future__ import annotations

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.cohere import CohereRerankProvider


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_cohere_returns_sorted_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.cohere.com"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "results": [
                {"index": 2, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.50},
                {"index": 1, "relevance_score": 0.10},
            ],
        })
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="test-key",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=3)
    assert indices == [2, 0, 1]


@pytest.mark.asyncio
async def test_cohere_auth_error_on_401() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="bad",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_cohere_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_cohere_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_cohere_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")
    provider = CohereRerankProvider(
        model="rerank-v3.5", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
