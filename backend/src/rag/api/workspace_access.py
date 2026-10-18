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


async def require_writable_service_refs(
    request: Request, refs: list[str | None], default_vault_name: str
) -> None:
    """403 `foreign_vault_ref` si une ref écrite vise un coffre non modifiable.

    Voir `rag.services.secret_ref_guard` : sans ce contrôle, garder la ref
    d'un coffre d'autrui (ou la saisir) en changeant le `base_url` faisait
    envoyer sa clé vers un serveur choisi par l'appelant.
    """
    from rag.auth.owner import get_current_owner_id
    from rag.services.secret_ref_guard import (
        ForeignVaultRefError,
        db_require_writable_vault_refs,
    )

    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            await db_require_writable_vault_refs(
                conn,
                owner_id=get_current_owner_id(request),
                refs=refs,
                default_vault_name=default_vault_name,
            )
        except ForeignVaultRefError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, {"error": "foreign_vault_ref", "vault": exc.vault}
            ) from exc
