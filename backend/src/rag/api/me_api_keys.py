from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.user_api_keys import (
    GrantsUpdate,
    UserApiKeyCreate,
    UserApiKeyCreated,
    UserApiKeyOut,
    UserApiKeyRotated,
)
from rag.services import user_api_keys as svc

log = structlog.get_logger(__name__)


def build_me_api_keys_router() -> APIRouter:
    """Clés API personnelles de l'utilisateur connecté.

    Show-once : la valeur n'apparaît qu'à la création/rotation ; seule
    l'empreinte SHA-256 est stockée. Les droits (can_read/can_write) sont
    accordés par workspace via les grants.
    """
    router = APIRouter(
        prefix="/api/me/api-keys",
        tags=["me-api-keys"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    def _pool(request: Request) -> asyncpg.Pool:
        return request.app.state.pools.config_pool

    @router.get("", response_model=list[UserApiKeyOut])
    async def list_my_keys(request: Request) -> list[UserApiKeyOut]:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            return await svc.list_for_owner(conn, owner_id=owner_id)

    @router.post("", response_model=UserApiKeyCreated, status_code=201)
    async def create_my_key(req: UserApiKeyCreate, request: Request) -> UserApiKeyCreated:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            try:
                return await svc.create_key(conn, owner_id=owner_id, req=req)
            except svc.UnknownWorkspaceError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "une clé porte déjà ce nom"
                ) from exc

    @router.post("/{key_id}/rotate", response_model=UserApiKeyRotated)
    async def rotate_my_key(key_id: UUID, request: Request) -> UserApiKeyRotated:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            try:
                result = await svc.rotate_key(conn, owner_id=owner_id, key_id=str(key_id))
            except ValueError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
        return result

    @router.delete("/{key_id}", status_code=204)
    async def revoke_my_key(key_id: UUID, request: Request) -> Response:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            revoked = await svc.revoke_key(conn, owner_id=owner_id, key_id=str(key_id))
        if not revoked:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "api key not found or already revoked"
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.put("/{key_id}/workspaces", status_code=204)
    async def set_my_key_grants(
        key_id: UUID, req: GrantsUpdate, request: Request
    ) -> Response:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            try:
                updated = await svc.set_grants(
                    conn, owner_id=owner_id, key_id=str(key_id), req=req
                )
            except svc.UnknownWorkspaceError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        if not updated:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
