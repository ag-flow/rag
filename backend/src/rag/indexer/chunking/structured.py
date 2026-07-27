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
class RoutedRegion:
    """Région ayant matché une route (spec §3), rapportée pour le contextual
    retrieval « Prompt B » : un enrichissement `region:<type>[:<qualifier>]`
    en `embedding_inline` peut embedder une description LLM de la région.

    `source_embedded=False` (route `parent_only`) : le source n'est pas
    embeddé, la description le REMPLACE. `source_embedded=True` (atomique,
    cible, inline explicite) : la description s'AJOUTE au source embeddé.
    Les régions sans route ne sont pas rapportées : déclarer une route est
    le geste d'activation (dépendance F2 assumée par la spec).
    """

    region_type: str
    qualifier: str | None
    content: str
    parent_key: str
    crumb: tuple[str, ...]
    breadcrumb_depth: int
    source_embedded: bool


@dataclass(frozen=True)
class ChunkedDocument:
    """Résultat d'un découpage structure-aware : parents + enfants liés.

    `routed_regions` : régions ayant matché une route (vide pour les
    chunkers sans passe régions — comportement historique inchangé).
    """

    parents: list[ParentSection]
    children: list[ChildChunk]
    routed_regions: list[RoutedRegion] = field(default_factory=list)


class StructuredChunkerProtocol(Protocol):
    """Interface des chunkers structure-aware (small-to-big).

    Distinct de `ChunkerProtocol` (legacy, plat → list[Chunk]). Découpage
    déterministe : même entrée → même `ChunkedDocument`.
    """

    def chunk(self, content: str) -> ChunkedDocument:
        """Découpe `content`. Retourne un document vide si vide/whitespace."""
        ...
