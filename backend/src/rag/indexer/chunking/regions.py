from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

REGION_TYPES: frozenset[str] = frozenset(
    {"prose", "code_fence", "table", "frontmatter", "html_block"}
)
"""Taxonomie fermée des types de régions (v1, parser markdown).

`type` est fermé, `qualifier` est ouvert : mermaid n'est pas un type mais
`(code_fence, 'mermaid')`. La spécialisation vit dans le routage, pas ici —
évite l'explosion « un type par langage de fence ».
"""


@dataclass(frozen=True)
class Region:
    """Région typée produite par la passe 1 (segmentation pure).

    `heading_path` = breadcrumb au point d'ouverture de la région : une région
    routée ailleurs conserve son ancrage hiérarchique. `content` conserve les
    fins de ligne d'origine — la concaténation des `content` d'un document
    restitue la source, sans perte ni chevauchement. `start_line` / `end_line`
    sont 1-based inclusifs.
    """

    type: str
    qualifier: str | None
    content: str
    heading_path: list[str]
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if self.type not in REGION_TYPES:
            raise ValueError(f"unknown region type: {self.type!r}")


class RegionParser(Protocol):
    """Passe 1 pure : liste ordonnée de régions.

    Aucun découpage, aucune normalisation, aucun breadcrumb injecté — ces
    responsabilités restent aux chunkers en aval du routage.
    """

    slug: str
    region_types: frozenset[str]

    def parse(self, content: str) -> list[Region]:
        """Segmente `content` en régions ordonnées ; `[]` si contenu vide."""
        ...
