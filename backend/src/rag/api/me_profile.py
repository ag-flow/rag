from __future__ import annotations

import uuid

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_principal_email
from rag.services import user_profile as svc

log = structlog.get_logger(__name__)


class ProfileOut(BaseModel):
    username: str
    email: str
    # GUID d'identité OBO (contrat v6) — null tant que l'utilisateur n'en a pas posé.
    identity: str | None


class ProfileUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=320)
    # None = inchangé ; "" = effacer ; sinon GUID (posé ou généré côté IHM).
    identity: str | None = Field(default=None, max_length=128)


class GeneratedIdentity(BaseModel):
    identity: str


def build_me_profile_router() -> APIRouter:
    """Profil de l'utilisateur connecté : email (pivot d'identité, matching
    OIDC) + GUID d'identité (matching OBO des appels MCP, contrat v6)."""
    router = APIRouter(
        prefix="/api/me/profile",
        tags=["me-profile"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    def _pool(request: Request) -> asyncpg.Pool:
        return request.app.state.pools.config_pool

    def _email_or_403(request: Request) -> str:
        email = get_current_principal_email(request)
        if email is None:
            # Master key = identité machine : pas de profil humain.
            raise HTTPException(status.HTTP_403_FORBIDDEN, "no_human_session")
        return email

    @router.get("", response_model=ProfileOut)
    async def get_profile(request: Request) -> ProfileOut:
        email = _email_or_403(request)
        async with _pool(request).acquire() as conn:
            user = await svc.get_or_create_user(conn, email=email)
        return ProfileOut(
            username=user["username"], email=user["email"], identity=user["identity"]
        )

    @router.put("", response_model=ProfileOut)
    async def put_profile(req: ProfileUpdate, request: Request) -> ProfileOut:
        email = _email_or_403(request)
        async with _pool(request).acquire() as conn:
            try:
                user = await svc.update_profile(
                    conn, current_email=email, new_email=req.email, identity=req.identity
                )
            except svc.InvalidIdentityError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_identity"
                ) from exc
            except svc.IdentityTakenError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, "identity_taken") from exc
            except svc.EmailTakenError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, "email_taken") from exc
        log.info("user_profile.updated", email=user["email"], has_identity=bool(user["identity"]))
        return ProfileOut(
            username=user["username"], email=user["email"], identity=user["identity"]
        )

    @router.post("/generate-identity", response_model=GeneratedIdentity)
    async def generate_identity(request: Request) -> GeneratedIdentity:
        """Propose un GUID (non persisté : l'IHM le pose via PUT après revue)."""
        _email_or_403(request)
        return GeneratedIdentity(identity=str(uuid.uuid4()))

    return router
