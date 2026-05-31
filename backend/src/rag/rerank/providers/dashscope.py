from __future__ import annotations

from typing import Any

import httpx
import structlog

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
)

log = structlog.get_logger(__name__)

_URL_INTERNATIONAL = (
    "https://dashscope-intl.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
)
_TIMEOUT = 30.0


class DashScopeRerankProvider:
    """Reranker Alibaba DashScope (gte-rerank-v2).

    Format natif DashScope — body : input.{query, documents} + parameters.top_n.
    Réponse : output.results[].{index, relevance_score}.
    Limites : 500 docs max, 30 000 tokens/requête, 4 000 tokens/doc.
    `base_url` configurable pour switcher région (défaut : international).
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._url = base_url or _URL_INTERNATIONAL
        self._transport = transport

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[int]:
        if not documents:
            return []
        body: dict[str, Any] = {
            "model": self._model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "top_n": min(top_k, len(documents)),
                "return_documents": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=_TIMEOUT,
            ) as client:
                resp = await client.post(self._url, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise RerankProviderUnreachable(f"dashscope timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"dashscope network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"dashscope auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("dashscope rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"dashscope 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"dashscope unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        results = data.get("output", {}).get("results", [])
        return [int(r["index"]) for r in results]
