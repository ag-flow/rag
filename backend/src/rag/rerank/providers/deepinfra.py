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

_DEFAULT_BASE_URL = "https://api.deepinfra.com"
_TIMEOUT = 30.0


class DeepInfraRerankProvider:
    """Reranker DeepInfra. API d'inférence par paires :
    POST /v1/inference/{model} avec {queries, documents} de même longueur
    (la requête est dupliquée pour chaque document) → {scores: [...]}.
    Le tri et le top_k sont donc appliqués côté client."""

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
        base = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._url = f"{base}/v1/inference/{model}"
        self._transport = transport

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[RerankResult]:
        if not documents:
            return []
        body: dict[str, Any] = {
            "queries": [query] * len(documents),
            "documents": documents,
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
            raise RerankProviderUnreachable(f"deepinfra timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"deepinfra network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"deepinfra auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("deepinfra rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"deepinfra 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"deepinfra unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        scores = data.get("scores", [])
        ranked = sorted(
            ((i, float(s)) for i, s in enumerate(scores)),
            key=lambda item: item[1],
            reverse=True,
        )
        return ranked[: min(top_k, len(documents))]
