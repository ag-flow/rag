from __future__ import annotations

import httpx
import pytest

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)
from rag.rerank.providers.voyage import VoyageRerankProvider


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_voyage_returns_sorted_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.voyageai.com"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "data": [
                {"index": 1, "relevance_score": 0.95},
                {"index": 2, "relevance_score": 0.80},
                {"index": 0, "relevance_score": 0.40},
            ],
        })
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="test-key",
        transport=_mock_transport(handler),
    )
    indices = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=3)
    assert indices == [1, 2, 0]


@pytest.mark.asyncio
async def test_voyage_auth_error_on_401() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(401)
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="bad",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_voyage_rate_limited_on_429() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(429)
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_voyage_unreachable_on_5xx() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(502)
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_voyage_unreachable_on_timeout() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")
    provider = VoyageRerankProvider(
        model="rerank-2", api_key="k",
        transport=_mock_transport(handler),
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
