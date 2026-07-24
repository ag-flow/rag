from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

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

    def _public_base(request: Request) -> str:
        """URL publique de base résolue depuis l'ADRESSE D'APPEL.

        On prend le Host réellement utilisé par le client (header `Host`, ou
        `X-Forwarded-Host` derrière proxy) + le schéma public — reflète le
        domaine exact (ex. https://rag.yoops.org), quelle que soit la config.

        Schéma : derrière un proxy public (`X-Forwarded-Host` présent), le TLS est
        terminé en amont (Cloudflare/Caddy) et le hop interne vers le backend est
        en HTTP — `X-Forwarded-Proto` reflète alors ce hop (`http`), pas l'entrée
        publique. On force donc `https` dès qu'on est derrière le proxy public.
        Sans proxy, on honore `X-Forwarded-Proto` (premier maillon si liste) puis
        l'URL de la requête."""
        fwd_host = request.headers.get("x-forwarded-host")
        host = fwd_host or request.headers.get("host")
        if not host:
            return str(request.base_url).rstrip("/")
        if fwd_host:
            scheme = "https"
        else:
            proto = request.headers.get("x-forwarded-proto")
            scheme = proto.split(",")[0].strip() if proto else request.url.scheme
        return f"{scheme}://{host}"

    @router.get("")
    async def contracts_index() -> dict[str, Any]:
        return {
            "rest": {
                "format": "openapi-3",
                "json": "/openapi.json",
                "swagger_ui": "/docs",
                "redoc": "/redoc",
            },
            "rest_apikey": {
                "format": "openapi-3",
                "json": "/api/contracts/openapi-apikey",
                "note": "Sous-ensemble : endpoints authentifiables par clé API utilisateur.",
            },
            "mcp": {
                "format": "mcp-tools",
                "tools": "/api/contracts/mcp-tools",
                "endpoint": "/mcp",
                "transport": "streamable-http",
                "auth": "Authorization: Bearer <clé API utilisateur (niveau read+)>",
            },
            "workflow_events": {
                "format": "openapi-3.1-webhooks",
                "json": "/api/contracts/workflow-events",
                "note": (
                    "Événements émis par ragflow vers ag.flow workflow (Porte A). "
                    "URL à importer sur la source inbound côté workflow."
                ),
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

    @router.get("/openapi-apikey")
    async def openapi_apikey(request: Request) -> dict[str, Any]:
        """OpenAPI filtré : uniquement les endpoints authentifiables par clé API.

        Sous-ensemble du contrat complet (`/openapi.json`) restreint aux
        opérations taguées `apikey` (recherche `/api/v1/search`, push/suppression
        d'index). Le serveur MCP protocolaire (`/mcp`, Bearer) est décrit à part
        via `/api/contracts/mcp-tools`."""
        full: dict[str, Any] = request.app.openapi()
        paths: dict[str, Any] = {}
        for path, operations in full.get("paths", {}).items():
            kept = {
                method: op
                for method, op in operations.items()
                if isinstance(op, dict) and "apikey" in (op.get("tags") or [])
            }
            if kept:
                paths[path] = kept
        info = dict(full.get("info", {}))
        info["title"] = "ragflow — API par clé API"
        info["description"] = (
            "Endpoints authentifiables par une clé API utilisateur (Bearer, ou "
            "api_key dans le corps pour /api/v1/search). Le connecteur MCP "
            "protocolaire /mcp est décrit via /api/contracts/mcp-tools."
        )
        return {
            "openapi": full.get("openapi", "3.1.0"),
            "info": info,
            # `servers` : sans lui l'outil consommateur ne connaît pas l'URL de
            # base et n'affiche aucune méthode appelable.
            "servers": [{"url": _public_base(request)}],
            "paths": paths,
            "components": full.get("components", {}),
        }

    @router.get("/openapi-apikey/docs", include_in_schema=False)
    async def openapi_apikey_docs() -> HTMLResponse:
        """Swagger UI du contrat filtré par clé API."""
        return get_swagger_ui_html(
            openapi_url="/api/contracts/openapi-apikey",
            title="ragflow — API par clé API (Swagger)",
        )

    @router.get("/workflow-events/docs", include_in_schema=False)
    async def workflow_events_docs() -> HTMLResponse:
        """Swagger UI du contrat d'events (webhooks OpenAPI 3.1)."""
        return get_swagger_ui_html(
            openapi_url="/api/contracts/workflow-events",
            title="ragflow — Events workflow (Swagger)",
        )

    @router.get("/workflow-events")
    async def workflow_events_contract() -> dict[str, Any]:
        """Contrat OpenAPI 3.1 des events émis vers workflow — sans auth.

        À importer sur la source inbound côté workflow (l'URL raw de cet
        endpoint est collable dans l'écran d'import)."""
        from rag.events.contract import build_events_contract

        return build_events_contract()

    return router
