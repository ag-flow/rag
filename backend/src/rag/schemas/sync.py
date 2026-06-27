from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChangeSet(BaseModel):
    """Résultat d'un diff git filtré (post `include` / `exclude`)."""

    model_config = ConfigDict(extra="forbid")

    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)

    @property
    def total_changed(self) -> int:
        return len(self.added) + len(self.modified) + len(self.deleted)


class GitOpResult(BaseModel):
    """Résultat d'un `ensure_clone_or_pull`."""

    model_config = ConfigDict(extra="forbid")

    was_fresh_clone: bool
    current_commit: str = Field(min_length=1)


class DueSource(BaseModel):
    """Une source dont `next_sync_at <= now()`, candidate pour scheduling."""

    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    workspace_id: UUID
    config: dict[str, Any]


class JobToProcess(BaseModel):
    """Contexte d'un job piké par l'executor (1 row JOIN workspace + indexer)."""

    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    workspace_id: UUID
    workspace_name: str
    source_id: UUID | None          # None pour les push jobs
    source_config: dict[str, Any]   # {} pour les push jobs
    indexer_provider: str
    indexer_model: str
    triggered_by: str
    correlation_id: str | None
    retry_count: int = 0

    @property
    def indexer_used(self) -> str:
        """Identifiant logique utilisé pour `indexed_documents.indexer_used`."""
        return f"{self.indexer_provider}/{self.indexer_model}"
