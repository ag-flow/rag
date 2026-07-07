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

_TIMEOUT = 30.0


class AzureFoundryRerankProvider:
    """Reranker Cohere déployé sur Azure AI Foundry.

    Azure expose plusieurs formes d'URL selon le type de déploiement
    (`{name}.{region}.models.ai.azure.com/v1/rerank` ou
    `{project}.services.ai.azure.com/providers/cohere/v2/rerank`), toutes
    Cohere-compatibles. On traite donc `base_url` comme l'URL **complète** de
    l'endpoint rerank (même précédent que dashscope), sans deviner de path.

    Auth : `Authorization: Bearer <clé de déploiement>` — aligné sur la
    plateforme azure-foundry côté embedding (BearerPlatform).
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._url = base_url.rstrip("/")
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
            raise RerankProviderUnreachable(f"azure-foundry timeout: {e}") from e
        except httpx.RequestError as e:
            raise RerankProviderUnreachable(f"azure-foundry network: {e}") from e

        if resp.status_code in (401, 403):
            raise RerankAuthError(f"azure-foundry auth: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise RerankRateLimited("azure-foundry rate limited (429)")
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(
                f"azure-foundry 5xx: HTTP {resp.status_code}"
            )
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"azure-foundry unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        results = data.get("results", [])
        return [(int(r["index"]), float(r.get("relevance_score", 0.0))) for r in results]
