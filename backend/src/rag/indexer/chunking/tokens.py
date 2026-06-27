from __future__ import annotations

import math
from typing import Protocol


class TokenEstimator(Protocol):
    """Estime le nombre de tokens d'un texte.

    Frontière pluggable : l'impl par défaut est heuristique (chars / ratio),
    mais on peut brancher un tokenizer exact (tiktoken, HF) sans toucher au
    pipeline de chunking, qui ne dépend que de cette interface.
    """

    def estimate(self, text: str) -> int:
        """Retourne une estimation >= 0 du nombre de tokens de `text`.

        Déterministe : même entrée → même sortie.
        """
        ...


class HeuristicTokenEstimator:
    """Estimateur heuristique : ``ceil(len(text) / char_ratio)``.

    `char_ratio` = nombre moyen de caractères par token pour le modèle visé
    (≈ 4.0 pour l'anglais/français en BPE OpenAI). Configurable par modèle via
    `model_dimensions.token_char_ratio`. L'imprécision est absorbée en aval par
    la marge de sécurité du plafond provider (cf. ADR 0001 §3).
    """

    def __init__(self, char_ratio: float = 4.0) -> None:
        if char_ratio <= 0:
            raise ValueError(f"char_ratio must be > 0, got {char_ratio}")
        self._char_ratio = char_ratio

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return math.ceil(len(text) / self._char_ratio)
