from __future__ import annotations

from typing import Literal

from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingBadRequest,
    EmbeddingProviderUnreachable,
    EmbeddingQuotaExhausted,
    EmbeddingRateLimited,
)

ErrorFamily = Literal["transient", "blocking", "permanent"]

# Transient : retry avec backoff
_TRANSIENT = (EmbeddingRateLimited, EmbeddingProviderUnreachable)

# Blocking : ouvre le circuit breaker du workspace
_BLOCKING = (EmbeddingAuthError, EmbeddingQuotaExhausted)

# Permanent : erreur structurelle non transitoire (ex. 4xx config invalide) →
# jamais de retry, jamais de circuit breaker "unreachable" trompeur
_PERMANENT = (EmbeddingBadRequest,)


def classify_indexer_error(exc: BaseException) -> ErrorFamily:
    """Classe une exception levée pendant l'indexation.

    - transient  : erreur temporaire (rate-limit, timeout, 503) → retry backoff
    - blocking   : erreur structurelle (credentials, quota épuisé) → circuit breaker
    - permanent  : tout le reste (dont config invalide : mauvais modèle, input
      rejeté) → error définitif sans retry
    """
    if isinstance(exc, _TRANSIENT):
        return "transient"
    if isinstance(exc, _BLOCKING):
        return "blocking"
    if isinstance(exc, _PERMANENT):
        return "permanent"
    return "permanent"
