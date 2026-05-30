from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.ssh_keys import SshKeyGenerate, SshKeyImport, SshKeyOut
from rag.services.ssh_keys import (
    DuplicateSshKeyError,
    delete_ssh_key,
    generate_ssh_key,
    import_ssh_key,
    list_ssh_keys,
)

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/{vault_id}/ssh-keys",
    tags=["admin-ssh-keys"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _vault_svc(request: Request) -> object:
    return request.app.state.harpocrate_vaults_service


@router.get("", response_model=list[SshKeyOut])
async def list_keys(vault_id: UUID, request: Request) -> list[SshKeyOut]:
    pool = _pool(request)
    async with pool.acquire() as conn:
        return await list_ssh_keys(conn, vault_id=str(vault_id))


@router.post("/import", response_model=SshKeyOut, status_code=201)
async def import_key(
    vault_id: UUID,
    body: SshKeyImport,
    request: Request,
) -> SshKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await import_ssh_key(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateSshKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/generate", response_model=SshKeyOut, status_code=201)
async def generate_key(
    vault_id: UUID,
    body: SshKeyGenerate,
    request: Request,
) -> SshKeyOut:
    pool = _pool(request)
    svc = _vault_svc(request)
    async with pool.acquire() as conn:
        vault = await svc.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        vault_dict = {"id": str(vault.id), "name": vault.name, "base_url": vault.base_url}
        try:
            return await generate_ssh_key(conn, vault=vault_dict, vault_svc=svc, req=body)
        except DuplicateSshKeyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


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
        deleted = await delete_ssh_key(
            conn, key_id=str(key_id), vault=vault_dict, vault_svc=svc
        )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ssh key not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
