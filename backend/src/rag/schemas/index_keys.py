from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class PathStrategyEntry(BaseModel):
    path: str
    strategy: Literal["replace", "append"]
    updated_by: Literal["ui", "strategy_file"]
    chunk_count: int
    version_count: int
    last_indexed_at: datetime | None


class IndexKeysResponse(BaseModel):
    paths: list[PathStrategyEntry]
    total: int


class ChunkEntry(BaseModel):
    chunk_index: int
    content: str
    metadata: dict[str, Any]
    indexed_at: datetime


class VersionGroup(BaseModel):
    indexed_at: datetime
    chunks: list[ChunkEntry]


class PathDetailResponse(BaseModel):
    path: str
    strategy: Literal["replace", "append"]
    updated_by: Literal["ui", "strategy_file"]
    versions: list[VersionGroup]


class StrategyPatchRequest(BaseModel):
    strategy: Literal["replace", "append"]
