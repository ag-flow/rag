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

_TIMEOUT = 30.0


class OllamaRerankProvider:
    """Reranker Ollama local (depuis Ollama 0.4+).

    Format de réponse de référence (à adapter si l'API Ollama évolue) :
        {"results": [{"index": int, "relevance_score": float}, ...]}
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[int]:
        if not documents:
            return []
        url = f"{self._base_url}/api/rerank"
        body: dict[str, Any] = {
            "model": self._model,
            "query": query,
            "documents": documents,
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT,
            ) as client:
                resp = await client.post(url, json=body)
        except httpx.TimeoutException as e:
            raise RerankProviderUnreachable(f"ollama timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"ollama network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"ollama auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("ollama rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"ollama 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"ollama unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        results = data.get("results", [])
        indices = [int(r["index"]) for r in results]
        return indices[:top_k]
