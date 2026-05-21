from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from rag.api.errors import (
    BootstrapDisabled,
    LocalAuthInvalidCredentials,
    LocalSessionExpired,
    OidcNotConfigured,
    OidcSessionExpired,
    OidcSessionMissing,
    OidcStateMismatch,
    OidcStateMissing,
)
from rag.auth.bearer import _LOCAL_SESSION_KEY
from rag.auth.oidc_dependency import require_oidc_role
from rag.schemas.local_auth import LocalLoginRequest, LocalLoginResponse
from rag.schemas.oidc import MeResponse

log = structlog.get_logger(__name__)

_SESSION_KEY = "_oidc_session"
_STATE_KEY = "_oidc_state"


def _safe_next(raw: str | None) -> str:
    """Anti open-redirect : accepter uniquement un path relatif `/...` qui
    ne commence pas par `//` (protocol-relative).
    Sinon retourne `/`."""
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw


def build_auth_router() -> APIRouter:
    """Router IHM (cookies session signés via SessionMiddleware Starlette)."""
    router = APIRouter(tags=["auth"])

    @router.get("/auth/login")
    async def login(request: Request, next: str = "/") -> RedirectResponse:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        url, state, nonce = await oidc.build_authorize_url()
        # Stocke (state, nonce, next) dans session signée (cookie HttpOnly).
        request.session[_STATE_KEY] = {
            "state": state,
            "nonce": nonce,
            "next": _safe_next(next),
        }
        return RedirectResponse(url=url, status_code=302)

    @router.get("/auth/callback")
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
    ) -> RedirectResponse:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        state_payload = request.session.get(_STATE_KEY)
        if not state_payload or not isinstance(state_payload, dict):
            raise OidcStateMissing()
        if not code or not state or state != state_payload.get("state"):
            raise OidcStateMismatch()

        tokens = await oidc.exchange_code(
            code=code,
            expected_nonce=state_payload["nonce"],
            config=cfg,
        )
        # Set session cookie (signée par SessionMiddleware).
        request.session[_SESSION_KEY] = {
            "id_token": tokens.id_token,
            "refresh_token": tokens.refresh_token,
            "exp": tokens.expires_at,
        }
        # Clear state payload
        request.session.pop(_STATE_KEY, None)

        next_path = _safe_next(state_payload.get("next"))
        return RedirectResponse(url=next_path, status_code=302)

    @router.post("/auth/refresh", status_code=status.HTTP_200_OK)
    async def refresh(request: Request) -> dict[str, bool]:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        session = request.session.get(_SESSION_KEY)
        if not session or not session.get("refresh_token"):
            raise OidcSessionMissing()

        try:
            tokens = await oidc.refresh(
                refresh_token=session["refresh_token"],
                config=cfg,
            )
        except OidcSessionExpired:
            request.session.pop(_SESSION_KEY, None)
            raise

        request.session[_SESSION_KEY] = {
            "id_token": tokens.id_token,
            "refresh_token": tokens.refresh_token or session["refresh_token"],
            "exp": tokens.expires_at,
        }
        return {"ok": True}

    @router.post("/auth/logout")
    async def logout(request: Request) -> Response:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        session = request.session.get(_SESSION_KEY)
        id_token = session.get("id_token") if session else None

        # Clear session locally
        request.session.pop(_SESSION_KEY, None)
        request.session.pop(_STATE_KEY, None)

        if cfg is not None and id_token:
            logout_url = await oidc.build_logout_url(id_token=id_token, config=cfg)
        else:
            logout_url = f"{request.app.state.public_url}/"
        return RedirectResponse(url=logout_url, status_code=302)

    @router.post("/auth/local/login", response_model=LocalLoginResponse)
    async def local_login(payload: LocalLoginRequest, request: Request) -> LocalLoginResponse:
        local_auth = request.app.state.local_auth
        if not local_auth.enabled:
            raise BootstrapDisabled()
        if not local_auth.verify(username=payload.username, password=payload.password):
            log.warning("auth.local.login.failure", username=payload.username)
            raise LocalAuthInvalidCredentials()
        request.session[_LOCAL_SESSION_KEY] = local_auth.build_session_payload()
        log.info("auth.local.login.success", username=payload.username)
        return LocalLoginResponse()

    @router.post("/auth/local/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def local_logout(request: Request) -> Response:
        request.session.pop(_LOCAL_SESSION_KEY, None)
        log.info("auth.local.logout")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/me", response_model=MeResponse)
    async def me(request: Request) -> MeResponse:
        local_session = request.session.get(_LOCAL_SESSION_KEY)
        if local_session:
            expires_at = local_session.get("expires_at", 0)
            if expires_at > int(time.time()):
                return MeResponse(
                    sub=local_session["username"],
                    email=None,
                    name=None,
                    roles=["rag-admin"],
                )
            request.session.pop(_LOCAL_SESSION_KEY, None)
            raise LocalSessionExpired()

        # Délègue au chemin OIDC existant
        oidc_dep = require_oidc_role("rag-viewer")
        user = await oidc_dep(request)
        return MeResponse(
            sub=user.sub,
            email=user.email,
            name=user.name,
            roles=user.roles,
        )

    return router
