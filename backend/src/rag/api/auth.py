from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from rag.api.errors import (
    OidcNotConfigured,
    OidcSessionExpired,
    OidcSessionMissing,
    OidcStateMismatch,
    OidcStateMissing,
)
from rag.auth.oidc_dependency import require_oidc_role
from rag.schemas.oidc import MeResponse, OidcUserContext

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

    @router.get("/me", response_model=MeResponse)
    async def me(
        user: OidcUserContext = Depends(require_oidc_role("rag-viewer")),  # noqa: B008
    ) -> MeResponse:
        return MeResponse(
            sub=user.sub,
            email=user.email,
            name=user.name,
            roles=user.roles,
        )

    return router
