from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TEMPLATE_TIMINGS: frozenset[str] = frozenset({"post_index_metadata", "embedding_inline"})
_REGION_TARGET_RE = re.compile(
    r"^region:(prose|code_fence|table|frontmatter|html_block)(:[A-Za-z0-9_-]+)?$"
)


class PromptTemplateCreate(BaseModel):
    """Deux axes contextual retrieval (spec « Prompt B ») :

    - `target` : `document` | `chunk` | `region:<type>[:<qualifier>]` ;
    - `timing` : `post_index_metadata` (métadonnée séparée, existant) |
      `embedding_inline` (injecté dans le texte embeddé).
    Combinaisons supportées : (document, post_index_metadata),
    (chunk | region:*, embedding_inline).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=1, max_length=64)
    description: str | None = None
    metadata_key: str = Field(min_length=1, max_length=64)
    result_type: str = Field(default="text")
    result_schema: dict[str, Any] | None = None
    prompt: str = Field(min_length=1)
    target: str = "document"
    timing: str = "post_index_metadata"

    @field_validator("target")
    @classmethod
    def _known_target(cls, v: str) -> str:
        if v in ("document", "chunk") or _REGION_TARGET_RE.fullmatch(v):
            return v
        raise ValueError(f"target inconnu : {v!r}")

    @field_validator("timing")
    @classmethod
    def _known_timing(cls, v: str) -> str:
        if v not in TEMPLATE_TIMINGS:
            raise ValueError(f"timing inconnu : {v!r}")
        return v

    @model_validator(mode="after")
    def _supported_combo(self) -> PromptTemplateCreate:
        metadata_combo = self.timing == "post_index_metadata" and self.target == "document"
        inline_combo = self.timing == "embedding_inline" and self.target != "document"
        if not (metadata_combo or inline_combo):
            raise ValueError(
                "combinaison non supportée : document↔post_index_metadata, "
                "chunk|region:*↔embedding_inline"
            )
        return self


class PromptTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    prompt: str | None = None
    result_schema: dict[str, Any] | None = None


class PromptTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    language: str
    description: str | None
    metadata_key: str
    result_type: str
    result_schema: dict[str, Any] | None
    prompt: str
    target: str
    timing: str
    prompt_version: int
    is_system: bool
    used_by_triggers: int
    used_by_strategies: int = 0
    created_at: datetime
    updated_at: datetime


class TriggerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extension: str = Field(min_length=2, max_length=16)
    enabled: bool = True
    # Stratégie de chunking LIÉE PAR ID pour cette extension (spec chunking §5).
    strategy_id: UUID | None = None


class TriggerPatch(BaseModel):
    """`strategy_id=None` explicite retire le binding — distingué de « champ
    absent » via `model_fields_set` (même convention que StrategyPatch)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    strategy_id: UUID | None = None


class TriggerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    extension: str
    enabled: bool
    strategy_id: UUID | None = None
    created_at: datetime


class TriggerPromptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: UUID
    llm_id: UUID
    order_index: int = Field(ge=1)
    enabled: bool = True


class TriggerPromptPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    order_index: int | None = Field(default=None, ge=1)


class TriggerPromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    llm_id: UUID
    llm_provider: str
    llm_model: str
    order_index: int
    enabled: bool
