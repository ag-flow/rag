from __future__ import annotations

from fastapi import FastAPI

from rag.api.admin import build_admin_router


def test_build_admin_router_returns_router_with_workspaces_routes() -> None:
    app = FastAPI()
    router = build_admin_router()
    app.include_router(router)

    paths = {route.path for route in app.router.routes}  # type: ignore[attr-defined]
    assert "/workspaces" in paths
    assert "/workspaces/{name}" in paths
    assert "/workspaces/{name}/rotate-apikey" in paths


def test_build_admin_router_includes_sources_routes() -> None:
    app = FastAPI()
    app.include_router(build_admin_router())
    paths = {route.path for route in app.router.routes}  # type: ignore[attr-defined]
    assert "/workspaces/{name}/sources" in paths
    assert "/workspaces/{name}/sources/{source_id}" in paths
