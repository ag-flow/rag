from __future__ import annotations

from typing import Protocol


class EmbeddingProviderError(RuntimeError):
    """Base des erreurs provider d'embedding.

    Les sous-classes distinguent les causes courantes pour permettre au
    SyncWorker (M3) d'écrire un `error_message` typé dans `index_jobs`.
    """


class EmbeddingAuthError(EmbeddingProviderError):
    """HTTP 401/403 — API key invalide ou révoquée."""


class EmbeddingRateLimited(EmbeddingProviderError):  # noqa: N818
    """HTTP 429 — le quota a été atteint et le retry interne a échoué."""


class EmbeddingQuotaExhausted(EmbeddingProviderError):  # noqa: N818
    """HTTP 402 ou quota global épuisé — crédits insuffisants."""


class EmbeddingProviderUnreachable(EmbeddingProviderError):  # noqa: N818
    """Réseau down, timeout, ou HTTP 503 (provider en panne)."""


class EmbeddingProvider(Protocol):
    """Frontière commune entre `RealIndexer` (M4a) et les implémentations
    OpenAI / Voyage / Ollama.

    Chaque provider expose deux méthodes async :
    - `embed_texts(texts)` : indexation (documents).
    - `embed_query(text)` : recherche (M4c, query unique).

    Les batchs internes (max 100 pour OpenAI/Voyage, 1 pour Ollama) sont
    une décision d'implémentation invisible côté caller.
    """

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Retourne 1 vecteur (list[float]) par texte d'entrée, dans le
        même ordre que `texts`.

        Lève `EmbeddingProviderError` (ou sous-classe) sur échec.
        """
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed une query de recherche.

        Distinct de `embed_texts` pour permettre aux providers comme Voyage
        d'utiliser `input_type="query"` (meilleure qualité search vs document).
        Les providers sans distinction (OpenAI, Ollama) délèguent à
        `embed_texts([text])[0]`.
        """
        ...
