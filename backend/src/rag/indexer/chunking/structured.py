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
class DroppedRegion:
    """Région exclue de l'embedding par une route `parent_only` (spec §3).

    Restituée au LLM via la section parente, elle reste candidate au
    contextual retrieval « Prompt B » : un enrichissement `region:<type>` en
    `embedding_inline` peut embedder une description LLM à sa place.
    """

    region_type: str
    qualifier: str | None
    content: str
    parent_key: str
    crumb: tuple[str, ...]
    breadcrumb_depth: int


@dataclass(frozen=True)
class ChunkedDocument:
    """Résultat d'un découpage structure-aware : parents + enfants liés.

    `dropped_regions` : régions `parent_only` (vide pour les chunkers sans
    passe régions — comportement historique inchangé).
    """

    parents: list[ParentSection]
    children: list[ChildChunk]
    dropped_regions: list[DroppedRegion] = field(default_factory=list)


class StructuredChunkerProtocol(Protocol):
    """Interface des chunkers structure-aware (small-to-big).

    Distinct de `ChunkerProtocol` (legacy, plat → list[Chunk]). Découpage
    déterministe : même entrée → même `ChunkedDocument`.
    """

    def chunk(self, content: str) -> ChunkedDocument:
        """Découpe `content`. Retourne un document vide si vide/whitespace."""
        ...
