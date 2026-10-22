from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from rag.api.errors import (
    LocalAuthDisabled,
    LocalAuthInvalidCredentials,
    LocalSessionExpired,
    OidcIdentityRefused,
    OidcNotConfigured,
    OidcSessionExpired,
    OidcSessionMissing,
    OidcStateMismatch,
    OidcStateMissing,
    SetupRequired,
)
from rag.api.public_base import public_base_from_request
from rag.auth.bearer import _LOCAL_SESSION_KEY
from rag.auth.oidc_dependency import require_oidc_role
from rag.schemas.local_auth import LocalLoginRequest, LocalLoginResponse
from rag.schemas.oidc import MeResponse
from rag.services.oidc_identity import (
    OidcIdentityRefusedError,
    OidcLogin,
    ResolvedUser,
    resolve_oidc_user,
)
from rag.services.user_accounts import db_role_for_username

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


async def _resolve_login_user(request: Request, id_token: str, cfg: Any) -> ResolvedUser:
    """Compte local d'un login OIDC : ancrage (issuer, sub), pont email vérifié."""
    oidc = request.app.state.oidc
    claims = await oidc.verify_id_token(id_token, config=cfg)
    login = OidcLogin(
        issuer=str(claims["iss"]),
        sub=str(claims["sub"]),
        email=claims.get("email"),
        # Seul un booléen True vaut vérification : absent ou "true" en chaîne
        # ne suffisent pas à ouvrir le pont vers un compte existant.
        email_verified=claims.get("email_verified") is True,
        username=claims.get("preferred_username"),
        token_roles=tuple(oidc.extract_roles(claims, cfg.client_id)),
    )
    relink = request.app.state.admin_env.is_oidc_relink_enabled()
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            return await resolve_oidc_user(conn, login, relink_enabled=relink)
        except OidcIdentityRefusedError as exc:
            log.warning("auth.oidc.identity_refused", reason=exc.reason)
            raise OidcIdentityRefused(exc.reason) from exc


def build_auth_router() -> APIRouter:
    """Router IHM (cookies session signés via SessionMiddleware Starlette)."""
    router = APIRouter(tags=["auth"])

    @router.get("/auth/login")
    async def login(request: Request, next: str = "/") -> RedirectResponse:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        # redirect_uri effectif : URL publique fixée depuis l'IHM (admin.env),
        # sinon dérivée de l'ADRESSE D'APPEL — fiable même si le
        # RAG_PUBLIC_URL du .env est périmé (bug redirect_uri=localhost).
        public_base = request.app.state.admin_env.get_public_url() or public_base_from_request(
            request
        )
        redirect_uri = f"{public_base}/auth/callback"
        url, state, nonce = await oidc.build_authorize_url(redirect_uri=redirect_uri)
        # Stocke (state, nonce, next, redirect_uri) dans session signée : le
        # callback DOIT repasser exactement la même redirect_uri à l'échange.
        request.session[_STATE_KEY] = {
            "state": state,
            "nonce": nonce,
            "next": _safe_next(next),
            "redirect_uri": redirect_uri,
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
            redirect_uri=state_payload.get("redirect_uri"),
        )
        user = await _resolve_login_user(request, tokens.id_token, cfg)
        # Set session cookie (signée par SessionMiddleware). user_id et
        # owner_id viennent de la BASE (compte ancré sur issuer+sub) : ils ne
        # se recalculent plus depuis l'email du token à chaque requête.
        request.session[_SESSION_KEY] = {
            "id_token": tokens.id_token,
            "refresh_token": tokens.refresh_token,
            "exp": tokens.expires_at,
            "user_id": user.user_id,
            "owner_id": user.owner_id,
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
            # L'identité résolue au login ne change pas au rafraîchissement.
            "user_id": session.get("user_id"),
            "owner_id": session.get("owner_id"),
        }
        return {"ok": True}

    @router.post("/auth/logout")
    async def logout(request: Request) -> Response:
        """Logout unifié : purge la session OIDC ET la session locale.

        Le bouton de l'IHM poste toujours ici, quel que soit le mode de
        connexion — deviner le mode côté client (ex. `sub == "admin"`) laissait
        les sessions locales à username différent connectées (bug 2026-07-27).
        Session locale seule : pas de détour Keycloak, retour direct à l'app
        (l'AuthGuard renvoie au login)."""
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        session = request.session.get(_SESSION_KEY)
        id_token = session.get("id_token") if session else None

        # Clear session locally (OIDC + locale)
        request.session.pop(_SESSION_KEY, None)
        request.session.pop(_STATE_KEY, None)
        request.session.pop(_LOCAL_SESSION_KEY, None)

        # Base dérivée de l'ADRESSE D'APPEL (X-Forwarded-Host) : fiable même si
        # RAG_PUBLIC_URL est erroné (sinon le logout renvoyait sur localhost).
        public_base = public_base_from_request(request)
        if cfg is not None and id_token:
            logout_url = await oidc.build_logout_url(
                id_token=id_token, config=cfg, post_logout_redirect_uri=f"{public_base}/"
            )
        else:
            logout_url = f"{public_base}/"
        return RedirectResponse(url=logout_url, status_code=302)

    @router.post("/auth/local/login", response_model=LocalLoginResponse)
    async def local_login(payload: LocalLoginRequest, request: Request) -> LocalLoginResponse:
        if request.app.state.admin_env.is_local_auth_disabled():
            log.warning("auth.local.login.disabled", username=payload.username)
            raise LocalAuthDisabled()
        local_auth = request.app.state.local_auth
        if await local_auth.user_count() == 0:
            raise SetupRequired()
        email = await local_auth.verify(username=payload.username, password=payload.password)
        if email is None:
            log.warning("auth.local.login.failure", username=payload.username)
            raise LocalAuthInvalidCredentials()
        request.session[_LOCAL_SESSION_KEY] = local_auth.build_session_payload(
            payload.username, email, await local_auth.db_owner_id(payload.username)
        )
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
            username = local_session.get("username")
            if expires_at > int(time.time()) and username:
                # Rôle EN BASE, comme pour l'autorisation (ticket a138f63b).
                role = await db_role_for_username(
                    request.app.state.pools.config_pool, str(username)
                )
                return MeResponse(
                    sub=username,
                    email=None,
                    name=None,
                    roles=[role] if role else [],
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
