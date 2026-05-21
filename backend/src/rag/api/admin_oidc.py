from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from rag.api.errors import OidcNotConfigured
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.oidc import OidcConfigCreate, OidcConfigRead


def build_admin_oidc_router() -> APIRouter:
    """Router master-key : CRUD config OIDC (singleton)."""
    router = APIRouter(
        tags=["admin"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    @router.post("/oidc", status_code=status.HTTP_201_CREATED)
    async def post_oidc_config(payload: OidcConfigCreate, request: Request) -> OidcConfigRead:
        cfg = await request.app.state.oidc.upsert_config(
            issuer=str(payload.issuer),
            client_id=payload.client_id,
            client_secret_ref=payload.client_secret_ref,
        )
        return OidcConfigRead(
            issuer=cfg.issuer,
            client_id=cfg.client_id,
            client_secret_ref=cfg.client_secret_ref,
        )

    @router.get("/oidc")
    async def get_oidc_config(request: Request) -> OidcConfigRead:
        cfg = await request.app.state.oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()
        return OidcConfigRead(
            issuer=cfg.issuer,
            client_id=cfg.client_id,
            client_secret_ref=cfg.client_secret_ref,
        )

    return router
