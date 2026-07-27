from __future__ import annotations

import asyncpg
import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.events.config import get_config, put_config
from rag.events.egress import build_test_envelope, deliver
from rag.events.registry import KNOWN_EVENT_CODES
from rag.schemas.events import (
    EventsProducerResponse,
    EventsProducerSpec,
    TestConnectionResponse,
)

log = structlog.get_logger(__name__)


def build_events_producer_router() -> APIRouter:
    """Config du relais d'events rag → workflow (Porte A) + test de connectivité."""
    router = APIRouter(
        prefix="/api/admin/events-producer",
        tags=["events-producer"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    def _pool(request: Request) -> asyncpg.Pool:
        return request.app.state.pools.config_pool

    def _to_response(cfg: object) -> EventsProducerResponse:
        return EventsProducerResponse(
            enabled=cfg.enabled,  # type: ignore[attr-defined]
            workflow_base_url=cfg.workflow_base_url,  # type: ignore[attr-defined]
            source_id=cfg.source_id,  # type: ignore[attr-defined]
            secret_ref=cfg.secret_ref,  # type: ignore[attr-defined]
            source_uri=cfg.source_uri,  # type: ignore[attr-defined]
            events=cfg.events,  # type: ignore[attr-defined]
            known_events=sorted(KNOWN_EVENT_CODES),
        )

    @router.get("", response_model=EventsProducerResponse)
    async def get_events_producer(request: Request) -> EventsProducerResponse:
        async with _pool(request).acquire() as conn:
            return _to_response(await get_config(conn))

    @router.put("", response_model=EventsProducerResponse)
    async def put_events_producer(
        spec: EventsProducerSpec, request: Request
    ) -> EventsProducerResponse:
        # Garde-fou : la liste blanche ne peut contenir que des events connus.
        unknown = [e for e in spec.events if e not in KNOWN_EVENT_CODES]
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "unknown_events", "events": unknown},
            )
        async with _pool(request).acquire() as conn:
            cfg = await put_config(
                conn,
                enabled=spec.enabled,
                workflow_base_url=spec.workflow_base_url,
                source_id=spec.source_id,
                secret_ref=spec.secret_ref,
                source_uri=spec.source_uri,
                events=spec.events,
            )
        # Effet à chaud : la config est relue à l'émission ET par le worker.
        return _to_response(cfg)

    @router.post("/test-connection", response_model=TestConnectionResponse)
    async def test_connection(request: Request) -> TestConnectionResponse:
        """Signe et POST un event de test HORS outbox (event non catalogué)."""
        async with _pool(request).acquire() as conn:
            cfg = await get_config(conn)
        if not cfg.is_deliverable():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "producer_not_configured"},
            )
        resolver = request.app.state.resolver
        secret = await resolver.resolve_with_retry(cfg.secret_ref)
        raw = build_test_envelope(cfg.source_uri)
        async with httpx.AsyncClient() as client:
            result = await deliver(
                client,
                base_url=cfg.workflow_base_url,
                source_id=cfg.source_id,
                secret=secret,
                raw_body=raw,
            )
        return TestConnectionResponse(
            ok=result.delivered, status_code=result.status_code, detail=result.detail
        )

    return router
