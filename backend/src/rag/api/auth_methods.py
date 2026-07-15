from __future__ import annotations

from fastapi import APIRouter, Request

from rag.schemas.local_auth import AuthMethodsResponse


def build_auth_methods_router() -> APIRouter:
    """Router public (pas d'auth) qui expose les méthodes activées.

    Utilisé par le frontend pour décider quoi afficher sur /ui/login.
    """
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.get("/methods", response_model=AuthMethodsResponse)
    async def get_methods(request: Request) -> AuthMethodsResponse:
        oidc_cfg = await request.app.state.oidc.get_config()
        local_auth = request.app.state.local_auth
        count = await local_auth.user_count()
        disabled = request.app.state.settings.rag_local_auth_disabled
        return AuthMethodsResponse(
            oidc_configured=oidc_cfg is not None,
            local_auth_enabled=count > 0 and not disabled,
            local_auth_disabled_by_config=disabled,
            needs_setup=count == 0,
        )

    return router
