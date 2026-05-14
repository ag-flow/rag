from __future__ import annotations

import hmac

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
