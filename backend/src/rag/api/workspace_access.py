from __future__ import annotations

import asyncpg
from fastapi import HTTPException, Request, status


async def require_owned_workspace_id(
    request: Request, name: str, pool: asyncpg.Pool
) -> object:
    """Garde de visibilité owner pour les endpoints workspace-scopés.

    Retourne l'id du workspace s'il est visible par le caller (partagé ou
    sien), sinon lève 404 ``workspace_not_found`` — un workspace d'autrui
    doit paraître inexistant (jamais accessible par son nom).
    """
    from rag.auth.owner import get_current_owner_id
    from rag.services.workspaces import resolve_owned_workspace_id

    async with pool.acquire() as conn:
        ws_id = await resolve_owned_workspace_id(
            conn, name=name, owner_id=get_current_owner_id(request)
        )
    if ws_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="workspace_not_found"
        )
    return ws_id
