from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from rag.indexer.chunking.regions import REGION_TYPES

OVERFLOW_POLICIES: frozenset[str] = frozenset({"keep_whole", "split_fallback", "parent_only"})
WILDCARD_QUALIFIER = "*"


@dataclass(frozen=True)
class RegionRoute:
    """Route d'une région vers son traitement (miroir de `chunking_strategy_region_routes`).

    - `target_strategy_id` : sous-chunker du catalogue appliqué au contenu de la
      région (profondeur 1 — le `parser_slug` éventuel de la cible est ignoré).
    - `target_strategy_id` NULL + `atomic` : région insécable traitée inline.
    - `overflow_policy` : sort de la région face au plafond dur provider —
      `keep_whole` (erreur typée), `split_fallback` (renonce à l'atomicité),
      `parent_only` (restituée au LLM via la section parente, jamais embeddée).
    """

    region_type: str
    qualifier: str = WILDCARD_QUALIFIER
    target_strategy_id: UUID | None = None
    atomic: bool = False
    overflow_policy: str = "keep_whole"

    def __post_init__(self) -> None:
        if self.region_type not in REGION_TYPES:
            raise ValueError(f"unknown region type: {self.region_type!r}")
        if not self.qualifier:
            raise ValueError("qualifier must be non-empty ('*' for wildcard)")
        if self.overflow_policy not in OVERFLOW_POLICIES:
            raise ValueError(f"unknown overflow policy: {self.overflow_policy!r}")


def resolve_region_route(
    routes: Sequence[RegionRoute],
    *,
    region_type: str,
    qualifier: str | None,
) -> RegionRoute | None:
    """Résolution par spécificité décroissante (spec chunking §3).

    `(type, qualifier)` exact → `(type, '*')` → None (comportement inline par
    défaut de la stratégie). Une région sans qualifier ne peut matcher que le
    wildcard.
    """
    wildcard: RegionRoute | None = None
    for route in routes:
        if route.region_type != region_type:
            continue
        if qualifier is not None and route.qualifier == qualifier:
            return route
        if wildcard is None and route.qualifier == WILDCARD_QUALIFIER:
            wildcard = route
    return wildcard
