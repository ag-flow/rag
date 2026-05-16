from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag.auth.bearer import require_master_key_or_oidc_role
from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultRevealApiKeyResponse,
    VaultRotateApiKeyRequest,
    VaultSummary,
    VaultTestConnectionResult,
    VaultUpdateRequest,
)
from rag.secrets.exceptions import (
    VaultNameAlreadyExistsError,
    VaultNotFoundError,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults",
    tags=["admin-harpocrate-vaults"],
    dependencies=[Depends(require_master_key_or_oidc_role("rag-admin"))],
)


def _actor(request: Request) -> str:
    """Déduit un identifiant d'actor simple pour les logs audit.

    M5c-backend : implémentation minimale. Un jalon ultérieur pourra
    raffiner en extrayant le sub OIDC depuis la session cookie.
    """
    if request.headers.get("Authorization"):
        return "master-key"
    return "oidc"


@router.get("", response_model=list[VaultSummary])
async def list_vaults(request: Request) -> list[VaultSummary]:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        return await svc.list_all(conn)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=VaultSummary)
async def create_vault(req: VaultCreateRequest, request: Request) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                v = await svc.create(conn, req)
        except VaultNameAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
    log.info("vault.created.http", vault_id=str(v.id), actor=actor)
    return v


@router.get("/{vault_id}", response_model=VaultSummary)
async def get_vault(vault_id: UUID, request: Request) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        v = await svc.get_by_id(conn, vault_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    return v


@router.patch("/{vault_id}", response_model=VaultSummary)
async def update_vault(vault_id: UUID, req: VaultUpdateRequest, request: Request) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    async with pool.acquire() as conn:
        v = await svc.update(conn, vault_id, req)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    log.info("vault.updated.http", vault_id=str(v.id), actor=actor)
    return v


@router.delete("/{vault_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vault(vault_id: UUID, request: Request) -> None:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    async with pool.acquire() as conn:
        target = await svc.get_by_id(conn, vault_id)
        if target is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        if target.is_default:
            others = await svc.list_all(conn)
            if len(others) > 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=("promouvoir un autre coffre via set-default avant suppression"),
                )
        deleted = await svc.delete(conn, vault_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    log.info("vault.deleted.http", vault_id=str(vault_id), actor=actor)


@router.post("/{vault_id}/rotate-api-key", response_model=VaultSummary)
async def rotate_api_key(
    vault_id: UUID, req: VaultRotateApiKeyRequest, request: Request
) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    async with pool.acquire() as conn:
        v = await svc.rotate_api_key(conn, vault_id, req)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    log.info("vault.api_key_rotated.http", vault_id=str(v.id), actor=actor)
    return v


@router.post("/{vault_id}/set-default", response_model=VaultSummary)
async def set_default(vault_id: UUID, request: Request) -> VaultSummary:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    async with pool.acquire() as conn:
        v = await svc.set_default(conn, vault_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    log.info("vault.default_changed.http", vault_id=str(v.id), actor=actor)
    return v


@router.post("/{vault_id}/test-connection", response_model=VaultTestConnectionResult)
async def test_connection(vault_id: UUID, request: Request) -> VaultTestConnectionResult:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        try:
            return await svc.test_connection(conn, vault_id)
        except VaultNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found") from exc


@router.get("/{vault_id}/api-key", response_model=VaultRevealApiKeyResponse)
async def reveal_api_key(vault_id: UUID, request: Request) -> VaultRevealApiKeyResponse:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    actor = _actor(request)
    async with pool.acquire() as conn:
        v = await svc.get_by_id(conn, vault_id)
        if v is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        api_key = await svc.reveal_api_key(conn, vault_id)
    log.warning("vault.reveal", vault_id=str(vault_id), actor=actor)
    return VaultRevealApiKeyResponse(id=v.id, api_key_id=v.api_key_id, api_key=api_key or "")
