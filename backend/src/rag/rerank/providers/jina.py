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

_DEFAULT_BASE_URL = "https://api.jina.ai/v1"
_PATH = "/rerank"
_TIMEOUT = 30.0


class JinaRerankProvider:
    """Reranker Jina AI. Modele par defaut : jina-reranker-v2-base-multilingual."""

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
        self,
        *,
        query: str,
        documents: list[str],
        top_k: int,
    ) -> list[RerankResult]:
        if not documents:
            return []
        body: dict[str, Any] = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": min(top_k, len(documents)),
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
            raise RerankProviderUnreachable(f"jina timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"jina network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"jina auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("jina rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"jina 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(f"jina unexpected {resp.status_code}: {resp.text}")

        data = resp.json()
        results = data.get("results", [])
        return [(int(r["index"]), float(r.get("relevance_score", 0.0))) for r in results]
