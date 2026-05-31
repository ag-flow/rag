from __future__ import annotations

import json as _json

import httpx
import pytest

from rag.rerank.providers.dashscope import DashScopeRerankProvider, _URL_INTERNATIONAL
from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)


def _ok_transport(indices: list[int]) -> httpx.MockTransport:
    payload = {
        "output": {
            "results": [{"index": i, "relevance_score": 1.0 - 0.1 * pos} for pos, i in enumerate(indices)]
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
async def test_rerank_returns_sorted_indices() -> None:
    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", transport=_ok_transport([2, 0, 1])
    )
    result = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=3)
    assert result == [2, 0, 1]


@pytest.mark.asyncio
async def test_rerank_empty_documents_returns_empty() -> None:
    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", transport=_ok_transport([])
    )
    result = await provider.rerank(query="q", documents=[], top_k=5)
    assert result == []


@pytest.mark.asyncio
async def test_rerank_top_k_clamped_to_doc_count() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = _json.loads(req.content)
        return httpx.Response(200, json={"output": {"results": [{"index": 0}]}})

    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", transport=httpx.MockTransport(handler)
    )
    await provider.rerank(query="q", documents=["a", "b"], top_k=100)
    assert captured["body"]["parameters"]["top_n"] == 2


@pytest.mark.asyncio
async def test_rerank_sends_correct_body_format() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = _json.loads(req.content)
        captured["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"output": {"results": [{"index": 0}]}})

    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="my-key", transport=httpx.MockTransport(handler)
    )
    await provider.rerank(query="ma query", documents=["doc1", "doc2"], top_k=2)
    assert captured["body"]["model"] == "gte-rerank-v2"
    assert captured["body"]["input"]["query"] == "ma query"
    assert captured["body"]["input"]["documents"] == ["doc1", "doc2"]
    assert captured["body"]["parameters"]["return_documents"] is False
    assert captured["auth"] == "Bearer my-key"


@pytest.mark.asyncio
async def test_rerank_uses_international_url_by_default() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json={"output": {"results": [{"index": 0}]}})

    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", transport=httpx.MockTransport(handler)
    )
    await provider.rerank(query="q", documents=["a"], top_k=1)
    assert captured["url"] == _URL_INTERNATIONAL


@pytest.mark.asyncio
async def test_rerank_uses_custom_base_url() -> None:
    custom = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(200, json={"output": {"results": [{"index": 0}]}})

    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", base_url=custom,
        transport=httpx.MockTransport(handler),
    )
    await provider.rerank(query="q", documents=["a"], top_k=1)
    assert captured["url"] == custom


@pytest.mark.asyncio
async def test_rerank_401_raises_auth_error() -> None:
    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="bad", transport=_status_transport(401)
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_rerank_403_raises_auth_error() -> None:
    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="bad", transport=_status_transport(403)
    )
    with pytest.raises(RerankAuthError):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_rerank_429_raises_rate_limited() -> None:
    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", transport=_status_transport(429)
    )
    with pytest.raises(RerankRateLimited):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_rerank_500_raises_unreachable() -> None:
    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", transport=_status_transport(500)
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)


@pytest.mark.asyncio
async def test_rerank_timeout_raises_unreachable() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = DashScopeRerankProvider(
        model="gte-rerank-v2", api_key="k", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(RerankProviderUnreachable):
        await provider.rerank(query="q", documents=["a"], top_k=1)
