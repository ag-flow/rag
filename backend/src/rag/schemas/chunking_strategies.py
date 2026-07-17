from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rag.indexer.chunking.region_routes import OVERFLOW_POLICIES, WILDCARD_QUALIFIER
from rag.indexer.chunking.regions import REGION_TYPES

ALGOS: frozenset[str] = frozenset({"prose", "markdown", "table", "code", "data"})


class RegionRouteSpec(BaseModel):
    """Route d'une région vers son traitement (spec chunking §3)."""

    model_config = ConfigDict(extra="forbid")

    region_type: str
    qualifier: str = Field(default=WILDCARD_QUALIFIER, min_length=1, max_length=64)
    target_strategy_id: UUID | None = None
    atomic: bool = False
    overflow_policy: str = "keep_whole"

    @field_validator("region_type")
    @classmethod
    def _known_region_type(cls, v: str) -> str:
        if v not in REGION_TYPES:
            raise ValueError(f"type de région inconnu : {v!r}")
        return v

    @field_validator("overflow_policy")
    @classmethod
    def _known_policy(cls, v: str) -> str:
        if v not in OVERFLOW_POLICIES:
            raise ValueError(f"politique de débordement inconnue : {v!r}")
        return v


class RoutesUpdate(BaseModel):
    """Remplacement complet du jeu de routes d'une stratégie."""

    model_config = ConfigDict(extra="forbid")

    routes: list[RegionRouteSpec]

    @model_validator(mode="after")
    def _unique_keys(self) -> RoutesUpdate:
        keys = [(r.region_type, r.qualifier) for r in self.routes]
        if len(keys) != len(set(keys)):
            raise ValueError("routes en double sur un même couple (type, qualifier)")
        return self


class StrategyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)
    algo: str
    params: dict[str, Any] = Field(default_factory=dict)
    parser_slug: str | None = None

    @field_validator("algo")
    @classmethod
    def _known_algo(cls, v: str) -> str:
        if v not in ALGOS:
            raise ValueError(f"algo inconnu : {v!r}")
        return v


class StrategyPatch(BaseModel):
    """Le slug n'est jamais saisi : un rename (label) le re-dérive serveur.

    `parser_slug=None` explicite retire la passe régions — distingué de
    « champ absent » via `model_fields_set`.
    """

    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=128)
    params: dict[str, Any] | None = None
    parser_slug: str | None = None


class StrategyDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)


class RegionRouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    region_type: str
    qualifier: str
    target_strategy_id: UUID | None
    atomic: bool
    overflow_policy: str


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    slug: str
    algo: str
    params: dict[str, Any]
    parser_slug: str | None
    is_system: bool
    used_by_routes: int
    used_by_categories: int
    used_by_triggers: int
    used_by_workspaces: int
    created_at: datetime
    updated_at: datetime


class StrategyDetailOut(StrategyOut):
    routes: list[RegionRouteOut]


class ParserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    label: str
