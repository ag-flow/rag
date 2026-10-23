"""Métadonnées de ressource protégée de la surface MCP (RFC 9728, ticket 3d457a26).

Route PUBLIQUE par nature : c'est ce qu'un client MCP lit avant d'avoir un
jeton, pour découvrir le serveur d'autorisation. Elle ne publie que des
valeurs publiques (identifiant de ressource, issuer).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from rag.api.public_base import public_base_from_request
from rag.auth.mcp_resource import (
    METADATA_PATH,
    RESOURCE_PATH,
    protected_resource_metadata,
    resource_uri,
)

router = APIRouter(tags=["oauth"])


async def _metadata(request: Request) -> dict[str, Any]:
    state = request.app.state
    config = await state.oidc.get_config()
    if config is None:
        # Sans IdP configuré, aucun jeton ne peut être accepté : annoncer un
        # serveur d'autorisation serait mentir au client.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "oidc_not_configured")
    base = state.admin_env.get_public_url() or public_base_from_request(request)
    resource = resource_uri(base, state.settings.rag_mcp_resource)
    return protected_resource_metadata(resource, config.issuer)


# RFC 9728 §3.1 : insertion du chemin de la ressource (`/mcp`) après le
# préfixe well-known. La racine est aussi servie : certains clients la
# demandent avant de suivre l'en-tête WWW-Authenticate.
@router.get(f"{METADATA_PATH}{RESOURCE_PATH}")
async def mcp_resource_metadata(request: Request) -> dict[str, Any]:
    return await _metadata(request)


@router.get(METADATA_PATH)
async def root_resource_metadata(request: Request) -> dict[str, Any]:
    return await _metadata(request)
