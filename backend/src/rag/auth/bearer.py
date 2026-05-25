from __future__ import annotations

import hmac
import time
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status


def require_master_key(request: Request) -> None:
    """Dependency FastAPI : valide `Authorization: Bearer <RAG_MASTER_KEY>`.

    Lit la master_key depuis `request.app.state.master_key` (injecté au lifespan).

    Réponses :
    - 401 `missing_bearer_token` si pas d'header.
    - 401 `invalid_auth_scheme` si header présent mais pas `Bearer`.
    - 401 `invalid_master_key` si token ne correspond pas.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_bearer_token",
        )

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_auth_scheme",
        )

    provided = parts[1].strip()
    expected = request.app.state.master_key
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_master_key",
        )


def require_master_key_or_oidc_role(
    role: str,
) -> Callable[[Request], Awaitable[None]]:
    """Dependency : accepte EITHER Bearer master-key OR cookie OIDC role.

    Priorité au Bearer si présent (cas machine/cURL/agents). Sinon délègue
    à `require_oidc_role(role)` qui vérifie le cookie de session.

    Retourne None dans tous les cas (le contexte user OIDC n'est pas
    propagé via cette dependency — utiliser `require_oidc_role` direct
    si besoin de l'identité du user).
    """
    # Import retardé pour éviter cycle (oidc_dependency dépend de
    # rag.api.errors qui dépend potentiellement de rag.auth).
    from rag.auth.oidc_dependency import require_oidc_role

    oidc_dep = require_oidc_role(role)

    async def _dep(request: Request) -> None:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            require_master_key(request)
            return None
        await oidc_dep(request)
        return None

    return _dep


_LOCAL_SESSION_KEY = "_local_session"


async def require_master_key_or_authenticated_admin(request: Request) -> None:
    """Dep : Bearer master-key OU session locale OU session OIDC rôle rag-admin.

    Ordre de résolution explicite :
    1. Si header Authorization présent → require_master_key (échec → 401, ne fallback PAS)
    2. Sinon si session locale présente et valide (expires_at > now) → ok
    3. Sinon si session locale présente mais expirée → clear + LocalSessionExpired (401)
    4. Sinon → require_oidc_role("rag-admin")
    """
    # Import retardé pour éviter cycle (oidc_dependency dépend de
    # rag.api.errors qui dépend potentiellement de rag.auth).
    from rag.api.errors import LocalSessionExpired
    from rag.auth.oidc_dependency import require_oidc_role

    auth_header = request.headers.get("Authorization")
    if auth_header:
        require_master_key(request)
        return None

    local_session = request.session.get(_LOCAL_SESSION_KEY)
    if local_session:
        expires_at = local_session.get("expires_at", 0)
        if expires_at > int(time.time()):
            return None
        request.session.pop(_LOCAL_SESSION_KEY, None)
        raise LocalSessionExpired()

    oidc_dep = require_oidc_role("rag-admin")
    await oidc_dep(request)
    return None
