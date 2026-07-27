from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.load_gate import LoadGateSettings, LoadGateStatusOut

log = structlog.get_logger(__name__)


def build_admin_load_gate_router() -> APIRouter:
    """Gate de charge serveur (enabler 01f8992b) : statut instantané + seuils
    pilotés par l'IHM (admin.env, relu à chaud — comme les réglages d'auth)."""
    router = APIRouter(
        tags=["admin-load-gate"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    def _status_out(request: Request) -> LoadGateStatusOut:
        status = request.app.state.load_gate.status()
        return LoadGateStatusOut(
            enabled=status.enabled,
            overloaded=status.overloaded,
            cpu_psi_avg60=status.cpu_psi_avg60,
            memory_used_pct=status.memory_used_pct,
            cpu_threshold_pct=status.cpu_threshold_pct,
            memory_threshold_pct=status.memory_threshold_pct,
            reasons=status.reasons,
        )

    @router.get("/load-gate", response_model=LoadGateStatusOut)
    async def get_load_gate(request: Request) -> LoadGateStatusOut:
        return _status_out(request)

    @router.put("/load-gate", response_model=LoadGateStatusOut)
    async def set_load_gate(payload: LoadGateSettings, request: Request) -> LoadGateStatusOut:
        request.app.state.admin_env.set_load_gate(
            enabled=payload.enabled,
            cpu_psi_pct=payload.cpu_threshold_pct,
            memory_pct=payload.memory_threshold_pct,
        )
        log.info(
            "load_gate.settings_updated",
            enabled=payload.enabled,
            cpu_threshold_pct=payload.cpu_threshold_pct,
            memory_threshold_pct=payload.memory_threshold_pct,
        )
        return _status_out(request)

    return router
