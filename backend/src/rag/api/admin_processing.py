from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.processing import ProcessingSettings, ProcessingStatusOut

log = structlog.get_logger(__name__)


def build_admin_processing_router() -> APIRouter:
    """Traitement global (feature a9719d13) : slots de jobs concurrents du
    worker, pilotés par l'IHM (admin.env, relu à chaud). Écran Configuration,
    admin uniquement — le paramétrage n'est PAS par workspace."""
    router = APIRouter(
        tags=["admin-processing"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    def _status_out(request: Request) -> ProcessingStatusOut:
        worker = getattr(request.app.state, "sync_worker", None)
        return ProcessingStatusOut(
            max_parallel_jobs=request.app.state.admin_env.get_worker_max_jobs(),
            active_jobs=worker.active_jobs if worker is not None else 0,
        )

    @router.get("/processing", response_model=ProcessingStatusOut)
    async def get_processing(request: Request) -> ProcessingStatusOut:
        return _status_out(request)

    @router.put("/processing", response_model=ProcessingStatusOut)
    async def set_processing(payload: ProcessingSettings, request: Request) -> ProcessingStatusOut:
        request.app.state.admin_env.set_worker_max_jobs(payload.max_parallel_jobs)
        log.info("processing.settings_updated", max_parallel_jobs=payload.max_parallel_jobs)
        return _status_out(request)

    return router
