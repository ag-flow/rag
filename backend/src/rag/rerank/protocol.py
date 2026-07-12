from __future__ import annotations

from typing import Protocol


class RerankProviderError(RuntimeError):
    """Base des erreurs reranker. Sous-classes : Auth / RateLimited / Unreachable."""


class RerankAuthError(RerankProviderError):
    """HTTP 401/403 — api_key invalide ou révoquée."""


class RerankRateLimited(RerankProviderError):  # noqa: N818
    """HTTP 429 — quota atteint."""


class RerankProviderUnreachable(RerankProviderError):  # noqa: N818
    """Timeout / connection refused / HTTP 5xx."""


RerankResult = tuple[int, float]
"""Paire ``(index, relevance_score)`` : `index` référence un document dans
`documents`, `relevance_score` est le score de pertinence renvoyé par le
provider (échelle propre au provider, typiquement 0..1). Utilisé pour peupler
`SearchHit.score` / `DebugTrace.rerank_score` (BUG-012)."""


class RerankProvider(Protocol):
    """Reranke des documents selon une query, retourne les paires
    ``(index, relevance_score)`` triées par pertinence décroissante.

    Convention : `len(retour) ≤ min(top_k, len(documents))`. Les indices
    sont dans `range(len(documents))`. L'ordre est strict : paire à
    position 0 = document le plus pertinent.
    """

    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[RerankResult]:
        ...
