from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Chunk:
    """Un chunk produit par un chunker. `metadata` est vide pour ParagraphChunker.

    metadata est exposé comme Mapping (contrat read-only). Les implémentations
    le construisent comme dict pour la commodité ; les consommateurs DOIVENT le
    traiter comme immutable. `frozen=True` empêche la réassignation de l'attribut
    mais pas la mutation in-place du dict sous-jacent — d'où l'annotation Mapping
    qui permet aux type-checkers de signaler toute tentative d'écriture.
    """

    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ChunkerProtocol(Protocol):
    """Interface des chunkers.

    Toute implémentation prend un texte et retourne une liste de `Chunk` avec un
    découpage déterministe (même entrée → même sortie).
    """

    def chunk(self, content: str) -> list[Chunk]:
        """Découpe `content`.

        Retourne `[]` si le contenu est vide ou whitespace-only. Implémentations
        libres de leur algorithme.
        """
        ...
