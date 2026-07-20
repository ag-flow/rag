from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter

log = structlog.get_logger(__name__)


def build_contracts_router() -> APIRouter:
    """Contrats d'API publics — accessibles SANS authentification.

    L'application expose ses contrats dans des documents normalisés :
    - REST : OpenAPI (généré par FastAPI) — /openapi.json, /docs, /redoc ;
    - MCP  : schéma des outils (format MCP `tools/list`) — figé ici en JSON
      pour être consultable sans clé API ni session.
    Cet index les référence pour la découverte programmatique et humaine.
    """
    router = APIRouter(prefix="/api/contracts", tags=["contracts"])

    @router.get("")
    async def contracts_index() -> dict[str, Any]:
        return {
            "rest": {
                "format": "openapi-3",
                "json": "/openapi.json",
                "swagger_ui": "/docs",
                "redoc": "/redoc",
            },
            "mcp": {
                "format": "mcp-tools",
                "tools": "/api/contracts/mcp-tools",
                "endpoint": "/mcp/{workspace_id}",
                "transport": "streamable-http",
                "auth": "Authorization: Bearer <clé API utilisateur (niveau read+)>",
            },
        }

    @router.get("/mcp-tools")
    async def mcp_tools_contract() -> dict[str, Any]:
        """Schéma des outils MCP (nom, description, inputSchema) — sans auth.

        Même matière que `tools/list` du protocole, mais consultable avant
        d'avoir une clé : ce que le serveur MCP saura faire une fois connecté.
        """
        from rag.api.mcp_standard import _mcp

        tools = await _mcp.list_tools()
        return {
            "format": "mcp-tools",
            "count": len(tools),
            "tools": [
                t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in tools
            ],
        }

    return router
