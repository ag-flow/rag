"""Partage des endpoints de coffre — routes IHM (migration 095, epic f3cc98a8).

- `GET  /api/admin/endpoints/usable` : endpoints utilisables par l'appelant
  (création de workspace) — possédés, du coffre par défaut, ou partagés ;
- `GET|PUT /api/admin/harpocrate-vaults/{vault_id}/endpoints/{endpoint_id}/sharing` :
  état de partage, lu et remplacé par le PROPRIÉTAIRE du coffre seulement ;
- `GET  /api/admin/endpoint-share-candidates?email=` : un utilisateur existant
  désigné par son email exact — jamais la liste des comptes.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from rag.api.admin_harpocrate_vaults import _check_vault_access
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id, principal_to_owner_id
from rag.schemas.endpoint_sharing import (
    EndpointSharingOut,
    EndpointSharingUpdate,
    ServiceModel,
    ShareUser,
    UsableEndpointOut,
)
from rag.services import endpoint_sharing as svc
from rag.services.endpoint_sharing import UsableEndpoint
from rag.services.vault_endpoints import get_endpoint

router = APIRouter(
    prefix="/api/admin",
    tags=["admin-endpoint-sharing"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool


def _service(spec: tuple[str, str] | None) -> ServiceModel | None:
    return None if spec is None else ServiceModel(provider=spec[0], model=spec[1])


def _to_out(ep: UsableEndpoint) -> UsableEndpointOut:
    return UsableEndpointOut(
        id=ep.id,
        slug=ep.slug,
        label=ep.label,
        vault_id=ep.vault_id,
        vault_name=ep.vault_name,
        vault_label=ep.vault_label,
        access=ep.access,
        indexer=ServiceModel(provider=ep.indexer[0], model=ep.indexer[1]),
        rerank=_service(ep.rerank),
        llm=_service(ep.llm),
    )


@router.get("/endpoints/usable", response_model=list[UsableEndpointOut])
async def list_usable_endpoints(request: Request) -> list[UsableEndpointOut]:
    async with _pool(request).acquire() as conn:
        usable = await svc.db_list_usable_endpoints(conn, owner_id=get_current_owner_id(request))
    return [_to_out(ep) for ep in usable]


async def _owned_endpoint(request: Request, vault_id: UUID, endpoint_id: UUID) -> None:
    """404 si l'endpoint n'est pas dans ce coffre, 403 si le coffre n'est pas à l'appelant.

    Le partage est une écriture : un bénéficiaire ne peut ni lire la liste des
    autres bénéficiaires ni se l'attribuer — seul le propriétaire du coffre.
    """
    vaults = request.app.state.harpocrate_vaults_service
    async with _pool(request).acquire() as conn:
        vault = await vaults.get_by_id(conn, vault_id)
        endpoint = await get_endpoint(conn, endpoint_id=endpoint_id)
    if vault is None or endpoint is None or endpoint.vault_id != vault_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "endpoint not found")
    _check_vault_access(vault, get_current_owner_id(request))


@router.get(
    "/harpocrate-vaults/{vault_id}/endpoints/{endpoint_id}/sharing",
    response_model=EndpointSharingOut,
)
async def get_sharing(vault_id: UUID, endpoint_id: UUID, request: Request) -> EndpointSharingOut:
    await _owned_endpoint(request, vault_id, endpoint_id)
    async with _pool(request).acquire() as conn:
        return await svc.db_get_sharing(conn, endpoint_id=endpoint_id)


@router.put(
    "/harpocrate-vaults/{vault_id}/endpoints/{endpoint_id}/sharing",
    response_model=EndpointSharingOut,
)
async def put_sharing(
    vault_id: UUID, endpoint_id: UUID, req: EndpointSharingUpdate, request: Request
) -> EndpointSharingOut:
    await _owned_endpoint(request, vault_id, endpoint_id)
    async with _pool(request).acquire() as conn:
        try:
            return await svc.db_set_sharing(conn, endpoint_id=endpoint_id, req=req)
        except svc.UnknownShareUserError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown_user") from exc


@router.get("/endpoint-share-candidates", response_model=ShareUser)
async def find_share_candidate(
    request: Request, email: str = Query(min_length=3, max_length=320)
) -> ShareUser:
    """Bénéficiaire désigné par son email exact — 404 sinon, jamais de liste."""
    async with _pool(request).acquire() as conn:
        user = await svc.db_find_share_candidate(conn, email=email.strip())
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found")
    if principal_to_owner_id(user.email) == get_current_owner_id(request):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "cannot_share_with_self")
    return user
