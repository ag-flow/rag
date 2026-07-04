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


class OllamaRerankProvider:
    """Reranker via un serveur compatible Ollama exposant ``POST /api/rerank``.

    ATTENTION (BUG-006) : Ollama **upstream n'expose PAS** d'endpoint natif de
    rerank — la feature request est ouverte de longue date et un Ollama standard
    répond 404 sur ``/api/rerank``. Ce provider cible donc un **fork** ou un
    **serveur tiers** compatible Ollama qui implémente cet endpoint. Un Ollama
    « embeddings only » ne convient pas : configurer plutôt un provider rerank
    dédié (cohere / jina / voyage / dashscope).

    Format de réponse attendu :
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
    ) -> list[RerankResult]:
        if not documents:
            return []
        url = f"{self._base_url}/api/rerank"
        top_n = min(top_k, len(documents))
        body: dict[str, Any] = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
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
        if resp.status_code == 404:
            # Cas le plus fréquent (BUG-006) : Ollama upstream n'implémente pas
            # /api/rerank. Message actionnable plutôt qu'un « unexpected 404 ».
            raise RerankProviderUnreachable(
                f"ollama /api/rerank introuvable (HTTP 404) à {url} : cet endpoint "
                "n'existe pas dans Ollama upstream. Un fork ou serveur tiers "
                "compatible exposant /api/rerank est requis, ou configurez un "
                "provider rerank dédié (cohere/jina/voyage/dashscope)."
            )
        if 500 <= resp.status_code < 600:
            raise RerankProviderUnreachable(f"ollama 5xx: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise RerankProviderUnreachable(
                f"ollama unexpected {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        results = data.get("results", [])
        # Défensif : ne pas se fier à l'ordre du serveur, trier explicitement
        # par relevance_score décroissant (format de réponse documenté).
        results = sorted(
            results, key=lambda r: float(r.get("relevance_score", 0.0)), reverse=True,
        )
        pairs: list[RerankResult] = [
            (int(r["index"]), float(r.get("relevance_score", 0.0))) for r in results
        ]
        return pairs[:top_k]
