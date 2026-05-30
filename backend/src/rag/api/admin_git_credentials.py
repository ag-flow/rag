from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.git_credentials import (
    GitCredentialCreate,
    GitCredentialOut,
    GitCredentialUpdate,
    GitCredentialWithVault,
)
from rag.services.git_credentials import (
    DuplicateGitCredentialError,
    GitCredentialReferencedError,
    create_git_credential,
    delete_git_credential,
    list_git_credentials,
    list_git_credentials_by_host,
    update_git_credential,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/{vault_id}/git-credentials",
    tags=["admin-git-credentials"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _vault_svc(request: Request) -> object:
    return request.app.state.harpocrate_vaults_service


@router.get("", response_model=list[GitCredentialOut])
async def list_keys(vault_id: UUID, request: Request) -> list[GitCredentialOut]:
    pool = _pool(request)
    async with pool.acquire() as conn:
        return await list_git_credentials(conn, vault_id=str(vault_id))


@router.post("", response_model=GitCredentialOut, status_code=201)
async def create_key(
    vault_id: UUID,
    body: GitCredentialCreate,
    request: Request,
) -> GitCredentialOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await create_git_credential(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateGitCredentialError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/{key_id}", response_model=GitCredentialOut)
async def update_key(
    vault_id: UUID,
    key_id: UUID,
    body: GitCredentialUpdate,
    request: Request,
) -> GitCredentialOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        result = await update_git_credential(
            conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc, req=body
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "git credential not found")
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
            deleted = await delete_git_credential(
                conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc
            )
        except GitCredentialReferencedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "git credential not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


router_global = APIRouter(
    prefix="/api/admin/git-credentials",
    tags=["admin-git-credentials"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


@router_global.get("/by-host", response_model=list[GitCredentialWithVault])
async def list_by_host(
    host: str,
    request: Request,
) -> list[GitCredentialWithVault]:
    pool = _pool(request)
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        rows = await list_git_credentials_by_host(conn, owner_id=owner_id, host=host)
    return [GitCredentialWithVault.model_validate(r) for r in rows]
