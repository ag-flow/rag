from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.provider_api_keys import (
    ProviderApiKeyCreate,
    ProviderApiKeyOut,
    ProviderApiKeyUpdate,
    ProviderApiKeyWithVault,
)
from rag.services.provider_api_keys import (
    DuplicateProviderKeyError,
    ProviderKeyReferencedError,
    create_provider_key,
    delete_provider_key,
    list_provider_keys,
    list_provider_keys_by_provider,
    update_provider_key,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/{vault_id}/provider-keys",
    tags=["admin-provider-keys"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


router_global = APIRouter(
    prefix="/api/admin/provider-keys",
    tags=["admin-provider-keys"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


@router_global.get("/by-provider", response_model=list[ProviderApiKeyWithVault])
async def list_by_provider(
    provider: str,
    request: Request,
) -> list[ProviderApiKeyWithVault]:
    pool = _pool(request)
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        rows = await list_provider_keys_by_provider(conn, owner_id=owner_id, provider=provider)
    return [ProviderApiKeyWithVault.model_validate(r) for r in rows]


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _vault_svc(request: Request) -> object:
    return request.app.state.harpocrate_vaults_service


@router.get("", response_model=list[ProviderApiKeyOut])
async def list_keys(vault_id: UUID, request: Request) -> list[ProviderApiKeyOut]:
    pool = _pool(request)
    async with pool.acquire() as conn:
        return await list_provider_keys(conn, vault_id=str(vault_id))


@router.post("", response_model=ProviderApiKeyOut, status_code=201)
async def create_key(
    vault_id: UUID,
    body: ProviderApiKeyCreate,
    request: Request,
) -> ProviderApiKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await create_provider_key(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateProviderKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/{key_id}", response_model=ProviderApiKeyOut)
async def update_key(
    vault_id: UUID,
    key_id: UUID,
    body: ProviderApiKeyUpdate,
    request: Request,
) -> ProviderApiKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        result = await update_provider_key(
            conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc, req=body
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider key not found")
    return result


@router.delete("/{key_id}", status_code=204)
async def delete_key(
    vault_id: UUID,
    key_id: UUID,
    request: Request,
) -> Response:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            deleted = await delete_provider_key(
                conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc
            )
        except ProviderKeyReferencedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider key not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
