from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.api.admin_harpocrate_vaults import _check_vault_access
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.vault_endpoints import EndpointCreate, EndpointOut, EndpointUpdate
from rag.services import vault_endpoints as svc
from rag.services.endpoint_fallback import EndpointFallbackInvalidError
from rag.services.endpoint_test import (
    EndpointTestRequest,
    EndpointTestResult,
    run_endpoint_test,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/{vault_id}/endpoints",
    tags=["admin-vault-endpoints"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


async def _checked_vault(request: Request, vault_id: UUID) -> None:
    """404 si le coffre n'existe pas, 403 si l'owner n'y a pas accès."""
    vaults = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        vault = await vaults.get_by_id(conn, vault_id)
    if vault is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    _check_vault_access(vault, get_current_owner_id(request))


@router.get("", response_model=list[EndpointOut])
async def list_endpoints(vault_id: UUID, request: Request) -> list[EndpointOut]:
    await _checked_vault(request, vault_id)
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        return await svc.list_endpoints(conn, vault_id=vault_id)


@router.post("", response_model=EndpointOut, status_code=201)
async def create_endpoint(vault_id: UUID, req: EndpointCreate, request: Request) -> EndpointOut:
    await _checked_vault(request, vault_id)
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        try:
            return await svc.create_endpoint(conn, vault_id=vault_id, req=req)
        except svc.EndpointSlugTakenError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"endpoint slug déjà pris : {exc}"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.patch("/{endpoint_id}", response_model=EndpointOut)
async def update_endpoint(
    vault_id: UUID, endpoint_id: UUID, req: EndpointUpdate, request: Request
) -> EndpointOut:
    await _checked_vault(request, vault_id)
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        try:
            updated = await svc.update_endpoint(conn, endpoint_id=endpoint_id, req=req)
        except EndpointFallbackInvalidError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "endpoint not found")
    return updated


@router.delete("/{endpoint_id}", status_code=204)
async def delete_endpoint(vault_id: UUID, endpoint_id: UUID, request: Request) -> Response:
    await _checked_vault(request, vault_id)
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        deleted = await svc.delete_endpoint(conn, endpoint_id=endpoint_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "endpoint not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/health")
async def endpoints_health(vault_id: UUID, request: Request) -> dict[str, dict[str, str]]:
    """État des breakers de fallback par endpoint du coffre (lot 3, f94bfd84).

    {endpoint_id: {service: closed|open|half_open}} — lecture pure du snapshot
    in-process, les services jamais sollicités sont absents (= closed)."""
    from rag.services.endpoint_breaker import get_breaker_registry

    await _checked_vault(request, vault_id)
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        eps = await svc.list_endpoints(conn, vault_id=vault_id)
    registry = get_breaker_registry()
    return {str(ep.id): registry.snapshot(str(ep.id)) for ep in eps}


@router.post("/test", response_model=EndpointTestResult)
async def test_endpoint(
    vault_id: UUID, req: EndpointTestRequest, request: Request
) -> EndpointTestResult:
    """Teste RÉELLEMENT la config saisie dans le formulaire (avant Save) :
    un embedding « ping » pour la vectorisation, un rerank de 2 documents pour
    le reranking. Retourne ok/message par section — le message d'échec porte le
    contexte (service appelé, modèle, réponse du provider)."""
    await _checked_vault(request, vault_id)
    return await run_endpoint_test(request, req)
