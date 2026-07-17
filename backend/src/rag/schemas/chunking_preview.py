from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CONTENT_MAX_CHARS = 1_000_000  # preview interactive — bien au-delà d'un doc courant


class PreviewRequest(BaseModel):
    """Dry-run de découpage : document échantillon + stratégie (spec §6 item 7)."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    strategy_id: UUID

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v) > _CONTENT_MAX_CHARS:
            raise ValueError("content_too_large")
        return v


class CompareRequest(BaseModel):
    """Deux stratégies côte à côte sur le même document."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    strategy_a: UUID
    strategy_b: UUID

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v) > _CONTENT_MAX_CHARS:
            raise ValueError("content_too_large")
        return v


class PreviewStrategyRef(BaseModel):
    id: UUID
    label: str
    slug: str
    algo: str
    parser_slug: str | None


class PreviewParent(BaseModel):
    section_key: str
    chars: int


class PreviewChunk(BaseModel):
    """Chunk embeddable avec ses frontières et son ancrage région éventuel."""

    index: int
    embed_text: str
    tokens: int
    chunk_hash: str
    parent_key: str
    region_type: str | None = None
    region_qualifier: str | None = None


class PreviewRegion(BaseModel):
    """Région détectée par le parser + route résolue (atomicité, politique)."""

    region_type: str
    qualifier: str | None
    start_line: int
    end_line: int
    routed: bool
    atomic: bool = False
    overflow_policy: str | None = None
    target_strategy_id: UUID | None = None


class PreviewResult(BaseModel):
    strategy: PreviewStrategyRef
    parents: list[PreviewParent]
    chunks: list[PreviewChunk]
    regions: list[PreviewRegion]
    total_chunks: int
    total_tokens: int


class ChunkSetDiff(BaseModel):
    """Diff ensembliste par chunk_hash (même sémantique que plan_children)."""

    common: int
    only_a: list[str]
    only_b: list[str]


class CompareResult(BaseModel):
    a: PreviewResult
    b: PreviewResult
    diff: ChunkSetDiff
