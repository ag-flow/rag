from __future__ import annotations

from typing import Any

import httpx
import structlog

from rag.rerank.protocol import (
    RerankAuthError,
    RerankProviderUnreachable,
    RerankRateLimited,
    RerankResult,
)

log = structlog.get_logger(__name__)

_DEFAULT_BASE_URL = "https://api.mixedbread.com"
_PATH = "/v1/reranking"
_TIMEOUT = 30.0


class MixedbreadRerankProvider:
    """Reranker Mixedbread (mxbai-rerank-v2). Body {model, query, input, top_k}
    → {data: [{index, score}]} (champ `input`, pas `documents` — API vérifiée
    sur le SDK officiel mixedbread-python)."""

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
        self._url = f"{(base_url or _DEFAULT_BASE_URL).rstrip('/')}{_PATH}"
        self._transport = transport

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[RerankResult]:
        if not documents:
            return []
        body: dict[str, Any] = {
            "model": self._model,
            "query": query,
            "input": documents,
            "top_k": min(top_k, len(documents)),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT,
            ) as client:
                resp = await client.post(self._url, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise RerankProviderUnreachable(f"mixedbread timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"mixedbread network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"mixedbread auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("mixedbread rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"mixedbread 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"mixedbread unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        results = data.get("data", [])
        return [(int(r["index"]), float(r.get("score", 0.0))) for r in results]
