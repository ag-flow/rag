from __future__ import annotations

from fastapi import APIRouter


def build_workspace_router() -> APIRouter:
    """Router des endpoints workspace authentifiés par api_key.

    Pour le moment : aucun endpoint implémenté.
    Task 7 récrira l'endpoint `POST /workspaces/{name}/index` avec
    la logique async (push_document → JobToProcess → Redis Streams).
    """
    router = APIRouter(tags=["workspace"])
    return router
