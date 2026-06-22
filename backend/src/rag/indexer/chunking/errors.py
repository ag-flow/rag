from __future__ import annotations


class ChunkingError(Exception):
    """Base des erreurs du domaine chunking."""


class ChunkTooLargeError(ChunkingError):
    """Une unité atomique (mot insécable) dépasse le plafond dur du provider.

    Levée plutôt que de tronquer ou de char-spliter un token au milieu :
    respecte l'invariant « aucune troncature silencieuse » (ADR 0001 §3). Le
    message porte l'estimation de tokens pour diagnostic dans `index_jobs`.
    """

    def __init__(self, *, estimated_tokens: int, hard_ceiling_tokens: int) -> None:
        super().__init__(
            f"atomic unit estimated at {estimated_tokens} tokens exceeds the provider "
            f"hard ceiling of {hard_ceiling_tokens} tokens and cannot be split further"
        )
        self.estimated_tokens = estimated_tokens
        self.hard_ceiling_tokens = hard_ceiling_tokens
