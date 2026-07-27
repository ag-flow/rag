from __future__ import annotations

import math
import unicodedata
from typing import Protocol

# Caractères « denses » : largeur East-Asian Wide (W) ou Fullwidth (F). Couvre les
# idéogrammes CJK, kana, hangul, formes fullwidth et la plupart des emoji — tous
# ~1 token/caractère en BPE, là où le latin fait ~4. Les caractères latins
# accentués (é, à, €) sont classés « Ambiguous » et donc traités comme du latin :
# aucune régression EN/FR (BUG-041).
_DENSE_WIDTHS = frozenset({"W", "F"})


def _dense_char_count(text: str) -> int:
    return sum(1 for c in text if unicodedata.east_asian_width(c) in _DENSE_WIDTHS)


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
    """Estimateur heuristique, conservateur pour les scripts denses.

    `char_ratio` = nombre moyen de caractères par token pour le modèle visé
    (≈ 4.0 pour l'anglais/français en BPE OpenAI). Configurable par modèle via
    `model_dimensions.token_char_ratio`.

    Un simple ``len / char_ratio`` sous-estime jusqu'à 4x le CJK, les emoji et
    les symboles denses (~1 char/token), laissant passer des blocs atomiques qui
    explosent la vraie limite d'input du provider (BUG-041). On sépare donc le
    comptage : caractères denses (Wide/Fullwidth) à 1 token chacun, le reste au
    `char_ratio`. Conservateur — jamais de sous-estimation sur les scripts denses,
    et strictement identique à l'ancien comportement pour l'EN/FR (0 dense).
    """

    def __init__(self, char_ratio: float = 4.0) -> None:
        if char_ratio <= 0:
            raise ValueError(f"char_ratio must be > 0, got {char_ratio}")
        self._char_ratio = char_ratio

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        dense = _dense_char_count(text)
        light = len(text) - dense
        return dense + math.ceil(light / self._char_ratio)
