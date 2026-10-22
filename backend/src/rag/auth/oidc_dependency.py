from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request

from rag.api.errors import (
    OidcInvalidToken,
    OidcNotConfigured,
    OidcRoleForbidden,
    OidcSessionExpired,
    OidcSessionMissing,
)
from rag.schemas.oidc import OidcUserContext
from rag.services.oidc_identity import db_role_for_user

_SESSION_KEY = "_oidc_session"


def _role_grants(required: str, *, user_roles: list[str]) -> bool:
    """Hierarchy : `rag-admin` grants `rag-viewer`."""
    admin_grants_viewer = required == "rag-viewer" and "rag-admin" in user_roles
    return required in user_roles or admin_grants_viewer


def require_oidc_role(
    role: str,
) -> Callable[[Request], Awaitable[OidcUserContext]]:
    """Factory de dependency FastAPI.

    Usage : `auth: OidcUserContext = Depends(require_oidc_role("rag-admin"))`.

    Raises (mappés en codes HTTP via le handler global) :
    - 401 OidcSessionMissing si cookie `_oidc_session` absent.
    - 401 OidcSessionExpired si id_token expiré (frontend doit POST /auth/refresh).
    - 401 OidcInvalidToken si signature/iss/aud invalides.
    - 403 OidcRoleForbidden si role insuffisant.
    - 503 OidcNotConfigured si oidc_config absent en DB.
    """

    async def _dep(request: Request) -> OidcUserContext:
        session = request.session.get(_SESSION_KEY)
        if not session:
            raise OidcSessionMissing()

        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        id_token = session.get("id_token")
        if not id_token:
            raise OidcSessionMissing()

        try:
            claims = await oidc.verify_id_token(id_token, config=cfg)
        except OidcInvalidToken as e:
            if e.reason == "expired":
                raise OidcSessionExpired() from e
            raise

        # Le token AUTHENTIFIE (signature, iss, aud, exp vérifiés ci-dessus) ;
        # c'est la BASE qui autorise (STANDARD OIDC §1, §9). Le rôle est relu
        # à chaque requête sur le compte ancré au login : une rétrogradation
        # s'applique tout de suite, et un IdP qui structure ses rôles autrement
        # ne retire à personne ses droits. Session sans user_id = ouverte avant
        # l'ancrage : on ne devine pas le compte, on fait se reconnecter.
        user_id = session.get("user_id")
        if not user_id:
            raise OidcSessionMissing()
        db_role = await db_role_for_user(request.app.state.pools.config_pool, user_id)
        user_roles = [db_role] if db_role else []
        if not _role_grants(role, user_roles=user_roles):
            raise OidcRoleForbidden(required=role, has=user_roles)

        return OidcUserContext(
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            roles=user_roles,
        )

    return _dep
