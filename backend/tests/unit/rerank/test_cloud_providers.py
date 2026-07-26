from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from rag.rerank.providers.deepinfra import DeepInfraRerankProvider
from rag.rerank.providers.fireworks import FireworksRerankProvider
from rag.rerank.providers.mixedbread import MixedbreadRerankProvider


def _mock_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_fireworks_cohere_format() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.fireworks.ai/inference/v1/rerank"
        assert request.headers["authorization"] == "Bearer fk-test"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ],
            },
        )

    provider = FireworksRerankProvider(
        model="accounts/fireworks/models/qwen3-reranker-8b",
        api_key="fk-test",
        transport=_mock_transport(handler),
    )
    results = await provider.rerank(query="q", documents=["a", "b"], top_k=2)
    assert results == [(1, 0.9), (0, 0.2)]


@pytest.mark.asyncio
async def test_deepinfra_pairs_and_client_side_sort() -> None:
    """DeepInfra score par paires : la requête est dupliquée par document,
    la réponse {scores} est triée et tronquée côté client."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"scores": [0.1, 0.8, 0.5]})

    provider = DeepInfraRerankProvider(
        model="Qwen/Qwen3-Reranker-8B",
        api_key="di-test",
        transport=_mock_transport(handler),
    )
    results = await provider.rerank(query="q", documents=["a", "b", "c"], top_k=2)
    assert seen["url"] == "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-8B"
    assert seen["body"] == {"queries": ["q", "q", "q"], "documents": ["a", "b", "c"]}
    assert results == [(1, 0.8), (2, 0.5)]


@pytest.mark.asyncio
async def test_mixedbread_input_field_and_score() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        assert str(request.url) == "https://api.mixedbread.com/v1/reranking"
        assert body["input"] == ["a", "b"]
        assert body["top_k"] == 2
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "score": 0.7}, {"index": 1, "score": 0.3}]},
        )

    provider = MixedbreadRerankProvider(
        model="mxbai-rerank-large-v2",
        api_key="mb-test",
        transport=_mock_transport(handler),
    )
    results = await provider.rerank(query="q", documents=["a", "b"], top_k=2)
    assert results == [(0, 0.7), (1, 0.3)]
