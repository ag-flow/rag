"""Administration des comptes et de leurs rôles (ticket a138f63b)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.services.user_accounts import (
    LastAdminError,
    UserAccount,
    UserNotFoundError,
    db_list_users,
    db_set_role,
)

# Réservé aux admins : la liste expose l'email de tous les comptes, qu'on ne
# montre jamais à un simple utilisateur (décision du 2026-10-18).
router = APIRouter(
    prefix="/api/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None = accès retiré : le compte reste (ses objets aussi), sans droits.
    role: Literal["rag-admin", "rag-viewer"] | None


@router.get("", response_model=list[UserAccount])
async def list_users(request: Request) -> list[UserAccount]:
    async with request.app.state.pools.config_pool.acquire() as conn:
        return await db_list_users(conn)


@router.patch("/{user_id}/role", response_model=UserAccount)
async def set_user_role(user_id: UUID, body: RoleUpdate, request: Request) -> UserAccount:
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            return await db_set_role(
                conn,
                user_id=user_id,
                role=body.role,
                actor_owner_id=get_current_owner_id(request),
            )
        except UserNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "user_not_found") from exc
        except LastAdminError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "last_admin") from exc
