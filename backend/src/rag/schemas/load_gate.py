from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoadGateSettings(BaseModel):
    """Seuils du gate de charge — persistés dans admin.env, relus à chaud."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    cpu_threshold_pct: int = Field(..., ge=1, le=100)
    memory_threshold_pct: int = Field(..., ge=1, le=100)
    io_threshold_pct: int = Field(default=60, ge=1, le=100)


class LoadGateStatusOut(BaseModel):
    """Statut instantané : métriques mesurées + seuils + verdict."""

    enabled: bool
    overloaded: bool
    cpu_psi_avg60: float | None
    memory_used_pct: float | None
    memory_source: Literal["cgroup", "meminfo"] | None = None
    io_psi_avg60: float | None
    cpu_threshold_pct: int
    memory_threshold_pct: int
    io_threshold_pct: int
    reasons: list[str]
    # Pause effective du worker (début, UTC) — distincte du verdict instantané :
    # le worker n'évalue le gate qu'à ses cycles de pick.
    worker_paused_since: datetime | None = None
