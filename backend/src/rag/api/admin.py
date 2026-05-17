from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_oidc_role
from rag.schemas.admin import (
    ApiKeyRotateResponse,
    JobResponse,
    ModelEntry,
    ReindexRequest,
    SourceCreateRequest,
    SourceResponse,
    WorkspaceCreateRequest,
    WorkspaceCreateResponse,
    WorkspacePatchRequest,
    WorkspaceResponse,
)
from rag.services.workspaces import (
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspaces,
    patch_workspace,
    rotate_apikey,
)


def _config_pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = request.app.state.pools.config_pool
    return pool


def _admin_dsn(request: Request) -> str:
    return str(request.app.state.admin_dsn)


def _resolver(request: Request) -> object:
    return request.app.state.resolver


async def _resolve_default_vault_or_503(request: Request) -> str:
    """Résout le coffre par défaut Harpocrate ou lève 503 si aucun n'est configuré.

    À appeler dans tout handler qui crée/modifie une ressource avec un secret.
    """
    provider = request.app.state.client_provider
    name = await provider.get_default_vault_name()
    if name is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "no_default_vault_configured"},
        )
    return name


def build_admin_router() -> APIRouter:
    """Construit le router master-key des 13 endpoints d'administration."""
    router = APIRouter(
        tags=["admin"],
        dependencies=[Depends(require_master_key_or_oidc_role("rag-admin"))],
    )

    # ─── Workspaces ─────────────────────────────────────────────────────────

    @router.post("/workspaces", status_code=status.HTTP_201_CREATED)
    async def post_workspaces(
        payload: WorkspaceCreateRequest,
        request: Request,
    ) -> WorkspaceCreateResponse:
        dek: str | None = request.app.state.settings.api_key_dek
        if dek is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="api_key_dek_unavailable",
            )
        default_vault = await _resolve_default_vault_or_503(request)
        resp = await create_workspace(
            request=payload,
            config_pool=_config_pool(request),
            admin_dsn=_admin_dsn(request),
            resolver=_resolver(request),  # type: ignore[arg-type]
            default_vault_name=default_vault,
            api_key_dek=dek,
        )
        return WorkspaceCreateResponse.model_validate(resp)

    @router.get("/workspaces")
    async def get_workspaces(request: Request) -> list[WorkspaceResponse]:
        rows = await list_workspaces(_config_pool(request))
        return [WorkspaceResponse(**r) for r in rows]  # type: ignore[arg-type]

    @router.get("/workspaces/{name}")
    async def get_workspace_detail(name: str, request: Request) -> WorkspaceResponse:
        row = await get_workspace(_config_pool(request), name=name)
        return WorkspaceResponse(**row)  # type: ignore[arg-type]

    @router.get("/workspaces/{name}/apikey")
    async def get_apikey_endpoint(name: str, request: Request) -> ApiKeyRotateResponse:
        """Retourne l'api_key en clair du workspace. Idempotent.

        Conforme spec 08 : sert à `init-rag.sh` côté ag.flow.docker pour
        provisionner `.rag-client.json` au démarrage container.
        """
        dek: str | None = request.app.state.settings.api_key_dek
        if dek is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="api_key_dek_unavailable",
            )
        row = await _config_pool(request).fetchrow(
            "SELECT pgp_sym_decrypt(api_key_encrypted, $2::text)::text AS api_key "
            "FROM workspaces WHERE name = $1",
            name, dek,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace_not_found",
            )
        return ApiKeyRotateResponse(api_key=row["api_key"])

    @router.patch("/workspaces/{name}")
    async def patch_workspace_endpoint(
        name: str, payload: WorkspacePatchRequest, request: Request
    ) -> WorkspaceResponse:
        default_vault = await _resolve_default_vault_or_503(request)
        await patch_workspace(
            name=name,
            request=payload,
            config_pool=_config_pool(request),
            resolver=_resolver(request),  # type: ignore[arg-type]
            default_vault_name=default_vault,
        )
        row = await get_workspace(_config_pool(request), name=name)
        return WorkspaceResponse(**row)  # type: ignore[arg-type]

    @router.delete("/workspaces/{name}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_workspace_endpoint(name: str, request: Request) -> Response:
        await delete_workspace(
            name=name,
            config_pool=_config_pool(request),
            admin_dsn=_admin_dsn(request),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/workspaces/{name}/rotate-apikey")
    async def rotate_apikey_endpoint(name: str, request: Request) -> ApiKeyRotateResponse:
        dek: str | None = request.app.state.settings.api_key_dek
        if dek is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="api_key_dek_unavailable",
            )
        new_key = await rotate_apikey(
            name=name,
            config_pool=_config_pool(request),
            api_key_dek=dek,
            apikey_cache=request.app.state.apikey_cache,
        )
        return ApiKeyRotateResponse(api_key=new_key)

    # ─── Sources ─────────────────────────────────────────────────────────────

    @router.post("/workspaces/{name}/sources", status_code=status.HTTP_201_CREATED)
    async def post_source(
        name: str, payload: SourceCreateRequest, request: Request
    ) -> SourceResponse:
        from rag.services.sources import add_source  # import retardé : évite cycle au boot

        default_vault = await _resolve_default_vault_or_503(request)
        row = await add_source(
            workspace_name=name,
            request=payload,
            config_pool=_config_pool(request),
            resolver=_resolver(request),  # type: ignore[arg-type]
            default_vault_name=default_vault,
        )
        return SourceResponse(**row)

    @router.delete(
        "/workspaces/{name}/sources/{source_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_source_endpoint(name: str, source_id: str, request: Request) -> Response:
        from rag.services.sources import delete_source

        await delete_source(
            workspace_name=name,
            source_id=source_id,
            config_pool=_config_pool(request),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ─── Reindex / Jobs ──────────────────────────────────────────────────────

    @router.post("/workspaces/{name}/reindex", status_code=status.HTTP_202_ACCEPTED)
    async def post_reindex(
        name: str,
        request: Request,
        payload: ReindexRequest | None = None,
        confirm: bool = False,
    ) -> JobResponse:
        from rag.services.jobs import reindex_workspace

        new_indexer = payload.indexer if payload is not None else None
        default_vault = await _resolve_default_vault_or_503(request)
        row = await reindex_workspace(
            name=name,
            new_indexer=new_indexer,
            confirm=confirm,
            config_pool=_config_pool(request),
            admin_dsn=_admin_dsn(request),
            resolver=_resolver(request),  # type: ignore[arg-type]
            default_vault_name=default_vault,
        )
        return JobResponse(**row)

    @router.get("/workspaces/{name}/jobs")
    async def get_jobs(name: str, request: Request) -> list[JobResponse]:
        from rag.services.jobs import list_jobs

        rows = await list_jobs(_config_pool(request), workspace_name=name)
        return [JobResponse(**r) for r in rows]

    # ─── Models registry ────────────────────────────────────────────────────

    @router.get("/admin/models")
    async def get_models(request: Request) -> list[ModelEntry]:
        from rag.services.models import list_models

        return await list_models(_config_pool(request))

    @router.post("/admin/models", status_code=status.HTTP_201_CREATED)
    async def post_model(payload: ModelEntry, request: Request) -> ModelEntry:
        from rag.services.models import add_model

        try:
            await add_model(
                _config_pool(request),
                provider=payload.provider,
                model=payload.model,
                dimension=payload.dimension,
            )
        except asyncpg.UniqueViolationError as e:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "model_already_exists",
                    "provider": payload.provider,
                    "model": payload.model,
                },
            ) from e
        return payload

    @router.delete(
        "/admin/models/{provider}/{model:path}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_model_endpoint(provider: str, model: str, request: Request) -> Response:
        from rag.services.models import delete_model

        await delete_model(_config_pool(request), provider=provider, model=model)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
