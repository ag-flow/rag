from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.admin_auth_config import (
    ClientSecretSet,
    ClientSecretStatus,
    LocalLoginSet,
    LocalLoginState,
)

log = structlog.get_logger(__name__)


def build_admin_auth_config_router() -> APIRouter:
    """Réglages d'auth pilotés par l'IHM et persistés dans admin.env.

    Master-key / admin authentifié. Le client secret OIDC et l'activation de la
    connexion locale sont écrits dans le fichier admin.env (relu à chaud).
    """
    router = APIRouter(
        tags=["admin-auth-config"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    @router.get("/oidc/client-secret", response_model=ClientSecretStatus)
    async def get_client_secret_status(request: Request) -> ClientSecretStatus:
        return ClientSecretStatus(
            configured=request.app.state.admin_env.has_oidc_client_secret()
        )

    @router.put("/oidc/client-secret", response_model=ClientSecretStatus)
    async def set_client_secret(payload: ClientSecretSet, request: Request) -> ClientSecretStatus:
        request.app.state.admin_env.set_oidc_client_secret(payload.value)
        log.info("oidc.client_secret.set")
        return ClientSecretStatus(configured=True)

    @router.get("/auth/local-login", response_model=LocalLoginState)
    async def get_local_login(request: Request) -> LocalLoginState:
        disabled = request.app.state.admin_env.is_local_auth_disabled()
        return LocalLoginState(enabled=not disabled)

    @router.put("/auth/local-login", response_model=LocalLoginState)
    async def set_local_login(payload: LocalLoginSet, request: Request) -> LocalLoginState:
        request.app.state.admin_env.set_local_auth_disabled(not payload.enabled)
        log.info("auth.local_login.set", enabled=payload.enabled)
        return LocalLoginState(enabled=payload.enabled)

    return router
