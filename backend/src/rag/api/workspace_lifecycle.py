"""Création et suppression de workspace par clé API utilisateur (/api/v1).

Décisions architecte (2026-09-30, ticket 21b879b5) :
- scope `read_write` ou `admin` — à l'inverse de l'outil MCP `create_workspace`,
  qui exige `admin`. Écart VOLONTAIRE : ne pas aligner sans nouvelle décision ;
- l'endpoint se désigne par coffre + slug, comme en MCP ;
- la suppression ne vise que les workspaces POSSÉDÉS et exige `confirm: true`.
"""

from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.workspace_auth import OwnerAuthContext, require_apikey_owner
from rag.schemas.admin import WorkspaceCreateResponse
from rag.schemas.workspace_lifecycle import (
    WorkspaceApikeyCreateRequest,
    WorkspaceApikeyDeleteRequest,
)
from rag.services import workspace_lifecycle as lifecycle
from rag.services import workspaces as workspaces_svc

log = structlog.get_logger(__name__)

_WRITE_SCOPES = ("read_write", "admin")

_AUTH_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {
        "description": "Clé absente ou invalide (`invalid_apikey`), ou clé de scope `read` "
        "(`insufficient_scope`)."
    },
    404: {"description": "Ressource introuvable ou non accessible à la clé."},
    422: {"description": "Corps invalide."},
}


def _require_write_scope(owner: OwnerAuthContext) -> None:
    # Même refus que l'ingestion (resolve_apikey_write_workspace) : 401 explicite,
    # distinct du 404 « introuvable », pour que l'appelant sache quoi corriger.
    if owner.scope not in _WRITE_SCOPES:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "insufficient_scope")


def build_workspace_lifecycle_router() -> APIRouter:
    router = APIRouter(tags=["apikey"])

    @router.post(
        "/workspaces",
        status_code=status.HTTP_201_CREATED,
        response_model=WorkspaceCreateResponse,
        summary="Créer un workspace",
        description="Crée un workspace possédé par le porteur de la clé (scope `read_write` "
        "ou `admin`). La configuration vectorisation / rerank / LLM de l'endpoint désigné "
        "par `vault` + `endpoint` est COPIÉE : une modification ultérieure de l'endpoint "
        "n'affecte pas le workspace. Une base pgvector dédiée est provisionnée et l'event "
        "`workspace_created` est émis vers workflow.",
        responses={
            **_AUTH_RESPONSES,
            404: {
                "description": "Coffre (`vault_not_found`) ou endpoint "
                "(`endpoint_not_found`) introuvable pour la clé."
            },
            409: {"description": "Slug déjà pris (`workspace_already_exists`)."},
        },
    )
    async def create_workspace(
        payload: WorkspaceApikeyCreateRequest,
        request: Request,
        owner: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> WorkspaceCreateResponse:
        _require_write_scope(owner)
        pool: asyncpg.Pool = request.app.state.pools.config_pool
        async with pool.acquire() as conn:
            endpoint = await lifecycle.resolve_endpoint_by_slug(
                conn, owner_id=owner.owner_id, vault=payload.vault, endpoint=payload.endpoint
            )
        resolved = workspaces_svc.resolved_from_endpoint(
            name=payload.name,
            label=payload.label or payload.name,
            description=payload.description,
            owner_id=owner.owner_id,
            endpoint=endpoint,
        )
        created = await workspaces_svc.create_workspace(
            request=resolved,
            config_pool=pool,
            admin_dsn=str(request.app.state.admin_dsn),
            resolver=request.app.state.resolver,
            harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
        )
        await lifecycle.emit_workspace_created(pool, resolved)
        log.info("apikey.workspace_created", workspace=payload.name, owner=owner.owner_id[:8])
        return WorkspaceCreateResponse.model_validate(created)

    @router.delete(
        "/workspaces",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Supprimer un workspace",
        description="Supprime un workspace POSSÉDÉ par le porteur de la clé (scope "
        "`read_write` ou `admin`) : base pgvector détruite, configuration, sources, jobs "
        "et documents supprimés. **Irréversible** — `confirm` doit valoir `true`. Un "
        "workspace partagé ou appartenant à autrui répond 404, comme un inexistant.",
        responses={
            **_AUTH_RESPONSES,
            404: {
                "description": "Workspace inexistant, partagé ou non possédé "
                "(`workspace_not_found`)."
            },
            422: {"description": "Corps invalide, dont `confirm` absent ou différent de true."},
        },
    )
    async def delete_workspace(
        payload: WorkspaceApikeyDeleteRequest,
        request: Request,
        owner: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> Response:
        _require_write_scope(owner)
        pool: asyncpg.Pool = request.app.state.pools.config_pool
        async with pool.acquire() as conn:
            await lifecycle.resolve_owned_workspace_for_deletion(
                conn, owner_id=owner.owner_id, workspace=payload.workspace
            )
        await workspaces_svc.delete_workspace(
            name=payload.workspace, config_pool=pool, admin_dsn=str(request.app.state.admin_dsn)
        )
        log.info("apikey.workspace_deleted", workspace=payload.workspace, owner=owner.owner_id[:8])
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
