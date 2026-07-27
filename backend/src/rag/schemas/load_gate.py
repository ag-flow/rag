from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoadGateSettings(BaseModel):
    """Seuils du gate de charge — persistés dans admin.env, relus à chaud."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    cpu_threshold_pct: int = Field(..., ge=1, le=100)
    memory_threshold_pct: int = Field(..., ge=1, le=100)


class LoadGateStatusOut(BaseModel):
    """Statut instantané : métriques mesurées + seuils + verdict."""

    enabled: bool
    overloaded: bool
    cpu_psi_avg60: float | None
    memory_used_pct: float | None
    cpu_threshold_pct: int
    memory_threshold_pct: int
    reasons: list[str]
