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

_URL = "https://api.voyageai.com/v1/rerank"
_TIMEOUT = 30.0


class VoyageRerankProvider:
    """Reranker Voyage AI v1."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._transport = transport

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[int]:
        if not documents:
            return []
        body: dict[str, Any] = {
            "query": query,
            "documents": documents,
            "model": self._model,
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
                resp = await client.post(_URL, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise RerankProviderUnreachable(f"voyage timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"voyage network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"voyage auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("voyage rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"voyage 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"voyage unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        items = data.get("data", [])
        return [int(r["index"]) for r in items]
