from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from rag.api.errors import HarpocrateUnreachableForApikey, VaultUnreachable
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.admin import (
    ApiKeyRotateResponse,
    ChunkingConfigResponse,
    ChunkingConfigSpec,
    JobFilesResponse,
    JobResponse,
    ModelEntry,
    ReindexRequest,
    RerankConfigResponse,
    RerankSpec,
    SourceCreateRequest,
    SourceResponse,
    SourceTestResult,
    SourceUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceCreateResponse,
    WorkspacePatchRequest,
    WorkspaceResponse,
)
from rag.secrets.refs import parse_ref
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
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    # ─── Workspaces ─────────────────────────────────────────────────────────

    @router.post("/workspaces", status_code=status.HTTP_201_CREATED)
    async def post_workspaces(
        payload: WorkspaceCreateRequest,
        request: Request,
    ) -> WorkspaceCreateResponse:
        resp = await create_workspace(
            request=payload,
            config_pool=_config_pool(request),
            admin_dsn=_admin_dsn(request),
            resolver=_resolver(request),  # type: ignore[arg-type]
            harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
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

        Résolution via cache process-lifetime → Harpocrate sur miss.
        """
        pool = _config_pool(request)
        row = await pool.fetchrow(
            "SELECT api_key_ref FROM workspaces WHERE name = $1", name
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace_not_found",
            )
        cache = request.app.state.apikey_cache
        api_key_ref: str = row["api_key_ref"]
        cached = cache.get(api_key_ref)
        if cached is None:
            try:
                cached = await request.app.state.resolver.resolve_with_retry(api_key_ref)
            except VaultUnreachable as e:
                raise HarpocrateUnreachableForApikey() from e
            cache.put(api_key_ref, cached)
        return ApiKeyRotateResponse(api_key=cached)

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
        pool = _config_pool(request)
        # Lire api_key_ref AVANT la suppression DB pour le rollback Harpocrate.
        ref_row = await pool.fetchrow(
            "SELECT api_key_ref FROM workspaces WHERE name = $1", name
        )
        await delete_workspace(
            name=name,
            config_pool=pool,
            admin_dsn=_admin_dsn(request),
        )
        # Suppression best-effort du secret Harpocrate (idempotent si absent).
        if ref_row is not None:
            try:
                vault_name, path = parse_ref(ref_row["api_key_ref"])
                async with pool.acquire() as conn:
                    await request.app.state.harpocrate_vaults_service.delete_secret(
                        conn, vault_name=vault_name, path=path
                    )
            except Exception:
                import structlog as _structlog
                _structlog.get_logger(__name__).warning(
                    "workspace.delete.harpocrate_cleanup_failed",
                    workspace=name,
                )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/workspaces/{name}/rotate-apikey")
    async def rotate_apikey_endpoint(name: str, request: Request) -> ApiKeyRotateResponse:
        result = await rotate_apikey(
            name=name,
            config_pool=_config_pool(request),
            harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
            apikey_cache=request.app.state.apikey_cache,
        )
        return ApiKeyRotateResponse(api_key=result["api_key"])

    # ─── Sources ─────────────────────────────────────────────────────────────

    @router.get("/workspaces/{name}/sources")
    async def list_sources_endpoint(name: str, request: Request) -> list[SourceResponse]:
        from rag.services.sources import list_sources

        rows = await list_sources(config_pool=_config_pool(request), workspace_name=name)
        return [SourceResponse(**r) for r in rows]

    @router.post("/workspaces/{name}/sources", status_code=status.HTTP_201_CREATED)
    async def post_source(
        name: str, payload: SourceCreateRequest, request: Request
    ) -> SourceResponse:
        from rag.services.sources import add_source  # import retardé : évite cycle au boot

        row = await add_source(
            workspace_name=name,
            request=payload,
            config_pool=_config_pool(request),
            harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
        )
        return SourceResponse(**row)

    @router.patch("/workspaces/{name}/sources/{source_id}")
    async def patch_source(
        name: str, source_id: str, payload: SourceUpdateRequest, request: Request
    ) -> SourceResponse:
        from rag.services.sources import update_source

        row = await update_source(
            workspace_name=name,
            source_id=source_id,
            request=payload,
            config_pool=_config_pool(request),
            harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
            resolver=request.app.state.resolver,
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

    @router.post("/workspaces/{name}/sources/{source_id}/test-connection")
    async def post_test_source_connection(
        name: str, source_id: str, request: Request
    ) -> SourceTestResult:
        from rag.services.sources import test_source_connection

        result = await test_source_connection(
            workspace_name=name,
            source_id=source_id,
            config_pool=_config_pool(request),
            resolver=request.app.state.resolver,
        )
        return SourceTestResult(**result)

    @router.post(
        "/workspaces/{name}/sources/{source_id}/sync",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def post_source_sync(name: str, source_id: str, request: Request) -> JobResponse:
        from rag.services.jobs import create_source_pending_job

        row = await create_source_pending_job(
            workspace_name=name,
            source_id=source_id,
            config_pool=_config_pool(request),
        )
        return JobResponse(**row)

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

    @router.get("/workspaces/{name}/jobs/{job_id}/files")
    async def get_job_files(name: str, job_id: str, request: Request) -> JobFilesResponse:
        from rag.services.jobs import list_job_files

        result = await list_job_files(
            config_pool=_config_pool(request),
            workspace_name=name,
            job_id=job_id,
        )
        return JobFilesResponse(**result)

    # ─── Models registry ────────────────────────────────────────────────────

    @router.get("/models")
    async def get_models(request: Request) -> list[ModelEntry]:
        from rag.services.models import list_models

        return await list_models(_config_pool(request))

    @router.post("/models", status_code=status.HTTP_201_CREATED)
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
        "/models/{provider}/{model:path}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_model_endpoint(provider: str, model: str, request: Request) -> Response:
        from rag.services.models import delete_model

        await delete_model(_config_pool(request), provider=provider, model=model)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ─── Rerank configs ─────────────────────────────────────────────────────

    @router.get("/workspaces/{name}/rerank")
    async def get_rerank_endpoint(name: str, request: Request) -> RerankConfigResponse:
        """Retourne la config rerank du workspace.

        404 `workspace_not_found` si le workspace n'existe pas.
        404 `rerank_not_configured` si le workspace existe mais sans rerank.
        """
        ws_row = await _config_pool(request).fetchrow(
            "SELECT id FROM workspaces WHERE name = $1",
            name,
        )
        if ws_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace_not_found",
            )
        from rag.services.rerank_configs import get_rerank_config

        cfg = await get_rerank_config(ws_row["id"], _config_pool(request))
        if cfg is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="rerank_not_configured",
            )
        return RerankConfigResponse(
            workspace_id=cfg["workspace_id"],
            provider=cfg["provider"],
            model=cfg["model"],
            api_key_ref=cfg["api_key_ref"],
            base_url=cfg["base_url"],
            top_k_pre_rerank=cfg["top_k_pre_rerank"],
            created_at=cfg["created_at"].isoformat(),
            updated_at=cfg["updated_at"].isoformat(),
        )

    @router.put("/workspaces/{name}/rerank")
    async def put_rerank_endpoint(
        name: str,
        payload: RerankSpec,
        request: Request,
    ) -> RerankConfigResponse:
        """Upsert la config rerank du workspace. Validation eager api_key_ref."""
        ws_row = await _config_pool(request).fetchrow(
            "SELECT id FROM workspaces WHERE name = $1",
            name,
        )
        if ws_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace_not_found",
            )
        from rag.services.rerank_configs import upsert_rerank_config

        cfg = await upsert_rerank_config(
            workspace_id=ws_row["id"],
            spec=payload,
            config_pool=_config_pool(request),
            resolver=_resolver(request),
            default_vault_name=await _resolve_default_vault_or_503(request),
        )
        return RerankConfigResponse(
            workspace_id=cfg["workspace_id"],
            provider=cfg["provider"],
            model=cfg["model"],
            api_key_ref=cfg["api_key_ref"],
            base_url=cfg["base_url"],
            top_k_pre_rerank=cfg["top_k_pre_rerank"],
            created_at=cfg["created_at"].isoformat(),
            updated_at=cfg["updated_at"].isoformat(),
        )

    @router.delete(
        "/workspaces/{name}/rerank",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_rerank_endpoint(name: str, request: Request) -> Response:
        """Supprime la config rerank. Idempotent : 204 même si absente."""
        ws_row = await _config_pool(request).fetchrow(
            "SELECT id FROM workspaces WHERE name = $1",
            name,
        )
        if ws_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace_not_found",
            )
        from rag.services.rerank_configs import delete_rerank_config

        await delete_rerank_config(ws_row["id"], _config_pool(request))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ─── Chunking config ────────────────────────────────────────────────────

    @router.get("/workspaces/{name}/chunking-config")
    async def get_chunking_config_endpoint(name: str, request: Request) -> ChunkingConfigResponse:
        """Retourne la chunking_config du workspace (cf. design M9 §5.2).

        Hydratée par défaut à la création du workspace (T6), donc présente dès
        le 201 POST /workspaces. 404 si workspace inconnu.
        """
        from rag.services.chunking_configs import get_chunking_config

        config_pool = _config_pool(request)
        ws_row = await config_pool.fetchrow("SELECT id FROM workspaces WHERE name = $1", name)
        if ws_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace_not_found",
            )
        cfg = await get_chunking_config(ws_row["id"], config_pool)
        return ChunkingConfigResponse(
            workspace_id=cfg["workspace_id"],
            strategy=cfg["strategy"],
            max_chars=cfg["max_chars"],
            min_chars=cfg["min_chars"],
            overlap_chars=cfg["overlap_chars"],
            extras=cfg["extras"],
            created_at=cfg["created_at"].isoformat(),
            updated_at=cfg["updated_at"].isoformat(),
        )

    @router.put("/workspaces/{name}/chunking-config")
    async def put_chunking_config_endpoint(
        name: str,
        payload: ChunkingConfigSpec,
        request: Request,
        confirm: bool = False,
    ) -> Response:
        """Upsert la chunking_config (cf. design M9 §5.2).

        - 204 si payload identique à la config courante.
        - 200 + ChunkingConfigResponse si changement sans documents indexés.
        - 409 ``chunking_change_requires_reindex`` si changement + docs > 0
          sans ``confirm=true`` (raised par ``apply_chunking_change``, mappé
          par ``register_error_handlers``).
        - 202 + JobResponse si changement + docs > 0 + ``confirm=true``.
        - 404 si workspace inconnu.
        - 422 si payload Pydantic invalide (validation DTO).
        """
        from rag.services.jobs import apply_chunking_change

        config_pool = _config_pool(request)
        ws_row = await config_pool.fetchrow("SELECT id FROM workspaces WHERE name = $1", name)
        if ws_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="workspace_not_found",
            )

        result = await apply_chunking_change(
            name=name, payload=payload, confirm=confirm, config_pool=config_pool
        )

        if result == "no_change":
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        tag, body = result
        if tag == "updated":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=ChunkingConfigResponse(
                    workspace_id=body["workspace_id"],
                    strategy=body["strategy"],
                    max_chars=body["max_chars"],
                    min_chars=body["min_chars"],
                    overlap_chars=body["overlap_chars"],
                    extras=body["extras"],
                    created_at=body["created_at"].isoformat(),
                    updated_at=body["updated_at"].isoformat(),
                ).model_dump(mode="json"),
            )
        # tag == "reindex_triggered" — body est un dict aligné JobResponse,
        # déjà ISO-formaté par jobs._job_to_dict.
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=JobResponse(**body).model_dump(mode="json"),
        )

    return router
