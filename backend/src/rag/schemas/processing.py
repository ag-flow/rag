from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProcessingSettings(BaseModel):
    """Réglages globaux de traitement (feature a9719d13) — admin.env, à chaud."""

    model_config = ConfigDict(extra="forbid")

    max_parallel_jobs: int = Field(..., ge=1, le=16)


class ProcessingStatusOut(BaseModel):
    """Réglages + occupation instantanée des slots du worker."""

    max_parallel_jobs: int
    active_jobs: int
