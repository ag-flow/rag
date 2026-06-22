from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ParentSection:
    """Section parente renvoyée au LLM (small-to-big, ADR 0001 §3 axe 2).

    `content` est le texte BRUT de la section (sans breadcrumb). `section_key`
    est l'identité stable de la section dans le fichier (slug du chemin de
    titres, suffixé `#n` en cas de doublon) — clé `(path, section_key)` côté DB.
    """

    section_key: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChildChunk:
    """Enfant embeddé : `embed_text` = breadcrumb + contenu normalisé.

    C'est `embed_text` qui est envoyé au provider d'embedding ET hashé pour le
    dédoublonnage incrémental (ADR 0001 §5). `parent_key` référence le
    `section_key` de la `ParentSection` à renvoyer au LLM.
    """

    embed_text: str
    parent_key: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkedDocument:
    """Résultat d'un découpage structure-aware : parents + enfants liés."""

    parents: list[ParentSection]
    children: list[ChildChunk]


class StructuredChunkerProtocol(Protocol):
    """Interface des chunkers structure-aware (small-to-big).

    Distinct de `ChunkerProtocol` (legacy, plat → list[Chunk]). Découpage
    déterministe : même entrée → même `ChunkedDocument`.
    """

    def chunk(self, content: str) -> ChunkedDocument:
        """Découpe `content`. Retourne un document vide si vide/whitespace."""
        ...
