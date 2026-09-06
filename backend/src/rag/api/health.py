from __future__ import annotations

import structlog
from fastapi import APIRouter, Request

log = structlog.get_logger(__name__)


def build_health_router() -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/version")
    def version(request: Request) -> dict[str, str]:
        return {
            "version": request.app.state.version,
            "git": request.app.state.git_sha,
            "environment": request.app.state.environment,
        }

    @router.get("/api/public/stats")
    async def public_stats(request: Request) -> dict[str, int | None]:
        """Métriques d'accueil de l'écran de connexion (feature 2ca3ceb8) —
        sans authentification, volontairement minimales (deux compteurs
        agrégés, aucun contenu). Fail-soft : None si la base est injoignable,
        l'écran affiche une cellule vide."""
        try:
            pool = request.app.state.pools.config_pool
            row = await pool.fetchrow(
                "SELECT (SELECT COUNT(*) FROM indexed_documents) AS documents, "
                "(SELECT COUNT(*) FROM workspaces) AS workspaces"
            )
            return {
                "indexed_documents": int(row["documents"]),
                "workspaces": int(row["workspaces"]),
            }
        except Exception:
            log.warning("public_stats.unavailable")
            return {"indexed_documents": None, "workspaces": None}

    return router
