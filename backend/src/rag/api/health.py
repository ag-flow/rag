from __future__ import annotations

from fastapi import APIRouter, Request


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

    return router
