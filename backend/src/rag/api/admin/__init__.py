from __future__ import annotations

import asyncio

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _PydanticBase

from rag.auth.admin_auth import require_admin
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.admin import (
    ChunkingConfigResponse,
    ChunkingConfigSpec,
    DefaultStrategyResponse,
    DefaultStrategySpec,
    EngineResponse,
    EngineSpec,
    HybridConfigResponse,
    HybridConfigSpec,
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
    WebhookEnableResponse,
    WorkspaceCreateRequest,
    WorkspaceCreateResponse,
    WorkspacePatchRequest,
    WorkspaceResponse,
)
from rag.secrets.resolver import VaultLookupFailed
from rag.services.workspaces import (
    create_workspace,
    delete_workspace,
    get_workspace,
    list_workspaces,
    patch_workspace,
)


class DetectBranchesRequest(_PydanticBase):
    url: str
    auth_ref: str | None = None
    ssh_key_ref: str | None = None
    ssh_username: str | None = None


class DetectBranchesResponse(_PydanticBase):
    branches: list[str]
    default: str | None


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
        # Résout l'endpoint choisi (préréglage du coffre) et copie sa config —
        # snapshot : les modifications ultérieures de l'endpoint n'affectent
        # pas ce workspace.
        from rag.schemas.admin import (
            IndexerCreateSpec,
            RerankCreateSpec,
            WorkspaceCreateResolved,
        )
        from rag.services.vault_endpoints import get_endpoint

        pool = _config_pool(request)
        async with pool.acquire() as conn:
            endpoint = await get_endpoint(conn, endpoint_id=payload.endpoint_id)
        if endpoint is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="endpoint_not_found")
        resolved = WorkspaceCreateResolved(
            name=payload.name,
            indexer=IndexerCreateSpec(
                provider=endpoint.indexer.provider,
                model=endpoint.indexer.model,
                api_key_ref=endpoint.indexer.api_key_ref,
                base_url=endpoint.indexer.base_url,
            ),
            rerank=(
                RerankCreateSpec(
                    provider=endpoint.rerank.provider,  # type: ignore[arg-type]
                    model=endpoint.rerank.model,
                    api_key_ref=endpoint.rerank.api_key_ref,
                    base_url=endpoint.rerank.base_url,
                    top_k_pre_rerank=endpoint.rerank.top_k_pre_rerank,
                )
                if endpoint.rerank is not None
                else None
            ),
        )
        resp = await create_workspace(
            request=resolved,
            config_pool=pool,
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
        # Les grants user_api_key_workspaces sont purgés par ON DELETE CASCADE.
        await delete_workspace(
            name=name,
            config_pool=_config_pool(request),
            admin_dsn=_admin_dsn(request),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

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
        from rag.auth.owner import get_current_owner_id
        from rag.services.sources import add_source  # import retardé : évite cycle au boot

        row = await add_source(
            workspace_name=name,
            request=payload,
            config_pool=_config_pool(request),
            harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
            owner_id=get_current_owner_id(request),
            resolver=request.app.state.resolver,
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

    # Schémas locaux pour detect-branches
    @router.post("/sources/detect-branches", response_model=DetectBranchesResponse)
    async def detect_branches(
        payload: DetectBranchesRequest,
        request: Request,
    ) -> DetectBranchesResponse:
        """Détecte les branches disponibles d'un dépôt Git via ls-remote."""
        import contextlib

        from rag.secrets.refs import is_vault_ref
        from rag.sync.git_ops import detect_default_branch, list_remote_branches

        # Validation anti-SSRF / argument injection
        url = payload.url.strip()
        if url.startswith("-"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid url")
        _allowed_schemes = ("https://", "http://", "git@", "ssh://", "git://")
        if not any(url.startswith(s) for s in _allowed_schemes):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid url scheme")

        token: str | None = None
        ssh_key: str | None = None
        ssh_username = payload.ssh_username or "git"

        # Résolution du credential.
        # Les harpo_path utilisent vault_name dans le ref (pas api_key_id).
        # On passe par harpocrate_vaults_service.get_by_name pour obtenir
        # l'api_key_id, puis client_provider.get_client(api_key_id).
        async def _resolve_secret(ref: str) -> str | None:
            from rag.secrets.refs import parse_ref as _parse_ref

            _vault_name, _secret_path = _parse_ref(ref)
            _pool = _config_pool(request)
            _svc = request.app.state.harpocrate_vaults_service
            async with _pool.acquire() as _conn:
                _vault = await _svc.get_by_name(_conn, _vault_name)
            if _vault is None:
                return None
            _client = await request.app.state.client_provider.get_client(_vault.api_key_id)
            return await asyncio.to_thread(_client.get_secret, _secret_path)

        if payload.ssh_key_ref and is_vault_ref(payload.ssh_key_ref):
            with contextlib.suppress(Exception):
                ssh_key = await _resolve_secret(payload.ssh_key_ref)
        elif payload.auth_ref and is_vault_ref(payload.auth_ref):
            with contextlib.suppress(Exception):
                token = await _resolve_secret(payload.auth_ref)

        branches_result, default_result = await asyncio.gather(
            list_remote_branches(
                url=payload.url,
                token=token,
                ssh_key=ssh_key,
                ssh_username=ssh_username,
            ),
            detect_default_branch(url=payload.url, token=token),
            return_exceptions=True,
        )

        branches: list[str] = branches_result if isinstance(branches_result, list) else []
        default: str | None = default_result if isinstance(default_result, str) else None

        return DetectBranchesResponse(branches=branches, default=default)

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

    @router.get("/models/pricing")
    async def get_models_pricing(request: Request) -> dict:
        from rag.services.pricing import load_pricing

        settings = request.app.state.settings
        return load_pricing(settings.pricing_file)

    @router.get("/models")
    async def get_models(request: Request) -> list[ModelEntry]:
        from rag.auth.owner import get_current_owner_id
        from rag.services.models import list_models

        return await list_models(_config_pool(request), owner_id=get_current_owner_id(request))

    @router.post("/models", status_code=status.HTTP_201_CREATED)
    async def post_model(payload: ModelEntry, request: Request) -> ModelEntry:
        from rag.auth.owner import get_current_owner_id
        from rag.services.models import add_model

        try:
            await add_model(
                _config_pool(request),
                provider=payload.provider,
                model=payload.model,
                dimension=payload.dimension,
                owner_id=get_current_owner_id(request),
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
        from rag.auth.owner import get_current_owner_id
        from rag.services.models import delete_model

        await delete_model(
            _config_pool(request),
            provider=provider,
            model=model,
            owner_id=get_current_owner_id(request),
        )
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
        name: str, payload: RerankSpec, request: Request
    ) -> RerankConfigResponse:
        """Insert ou update (upsert) la config rerank du workspace.

        404 `workspace_not_found` si le workspace n'existe pas.
        422 `invalid_api_key_ref` si api_key_ref ne résout pas dans le vault.
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
        from rag.services.rerank_configs import upsert_rerank_config

        default_vault = await _resolve_default_vault_or_503(request)
        try:
            cfg = await upsert_rerank_config(
                workspace_id=ws_row["id"],
                spec=payload,
                config_pool=_config_pool(request),
                resolver=_resolver(request),  # type: ignore[arg-type]
                default_vault_name=default_vault,
            )
        except (VaultLookupFailed, ConnectionError, TimeoutError) as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_api_key_ref",
            ) from e
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
        """Supprime la config rerank du workspace. Idempotent.

        404 `workspace_not_found` si le workspace n'existe pas ; sinon 204
        même si aucune config rerank n'était présente.
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
        from rag.services.rerank_configs import delete_rerank_config

        await delete_rerank_config(ws_row["id"], _config_pool(request))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ─── Hybrid search config ───────────────────────────────────────────────

    @router.get("/workspaces/{name}/hybrid-config")
    async def get_hybrid_config(
        name: str,
        request: Request,
        _: None = Depends(require_admin),
    ) -> HybridConfigResponse:
        pool: asyncpg.Pool = request.app.state.pools.config_pool
        ws = await pool.fetchrow("SELECT id FROM workspaces WHERE name = $1", name)
        if ws is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        row = await pool.fetchrow(
            "SELECT workspace_id, enabled, rrf_k, weight_lexical, weight_vector, "
            "lexical_engine, created_at, updated_at "
            "FROM hybrid_configs WHERE workspace_id = $1",
            ws["id"],
        )
        if row is None:
            raise HTTPException(status_code=404, detail="hybrid config not found")
        return HybridConfigResponse(
            workspace_id=str(row["workspace_id"]),
            enabled=row["enabled"],
            rrf_k=row["rrf_k"],
            weight_lexical=float(row["weight_lexical"]),
            weight_vector=float(row["weight_vector"]),
            lexical_engine=row["lexical_engine"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @router.put("/workspaces/{name}/hybrid-config")
    async def put_hybrid_config(
        name: str,
        spec: HybridConfigSpec,
        request: Request,
        _: None = Depends(require_admin),
    ) -> HybridConfigResponse:
        pool: asyncpg.Pool = request.app.state.pools.config_pool
        ws = await pool.fetchrow("SELECT id FROM workspaces WHERE name = $1", name)
        if ws is None:
            raise HTTPException(status_code=404, detail="workspace not found")
        # Bascule de moteur (D5) : vérifier la DISPONIBILITÉ avant d'écrire,
        # et reconstruire l'index lexical par un job — jamais de ré-embedding.
        previous = await pool.fetchval(
            "SELECT lexical_engine FROM hybrid_configs WHERE workspace_id = $1", ws["id"]
        )
        engine_changed = previous is not None and previous != spec.lexical_engine
        first_config = previous is None and spec.lexical_engine != "fts"
        rebuild_job_id: str | None = None
        if engine_changed or first_config:
            from rag.db.lexical_engines import get_lexical_engine

            ws_row = await pool.fetchrow("SELECT rag_cnx FROM workspaces WHERE id = $1", ws["id"])
            engine = get_lexical_engine(spec.lexical_engine)
            registry = request.app.state.pools
            ws_pool = await registry.get_workspace_pool(name, ws_row["rag_cnx"])
            async with ws_pool.acquire() as ws_conn:
                if not await engine.is_available(ws_conn):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "error": "lexical_engine_unavailable",
                            "engine": spec.lexical_engine,
                            "hint": "extension pg_search absente de cette instance "
                            "Postgres — voir l'aide de l'onglet Recherche",
                        },
                    )
            rebuild_job_id = str(
                await pool.fetchval(
                    "INSERT INTO index_jobs (workspace_id, triggered_by, status) "
                    "VALUES ($1, 'rebuild_lexical_index', 'pending') RETURNING id",
                    ws["id"],
                )
            )

        await pool.execute(
            """
            INSERT INTO hybrid_configs
                (workspace_id, enabled, rrf_k, weight_lexical, weight_vector, lexical_engine)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (workspace_id) DO UPDATE
            SET enabled = EXCLUDED.enabled,
                rrf_k = EXCLUDED.rrf_k,
                weight_lexical = EXCLUDED.weight_lexical,
                weight_vector = EXCLUDED.weight_vector,
                lexical_engine = EXCLUDED.lexical_engine,
                updated_at = now()
            """,
            ws["id"],
            spec.enabled,
            spec.rrf_k,
            spec.weight_lexical,
            spec.weight_vector,
            spec.lexical_engine,
        )
        row = await pool.fetchrow(
            "SELECT workspace_id, enabled, rrf_k, weight_lexical, weight_vector, "
            "lexical_engine, created_at, updated_at "
            "FROM hybrid_configs WHERE workspace_id = $1",
            ws["id"],
        )
        return HybridConfigResponse(
            workspace_id=str(row["workspace_id"]),
            enabled=row["enabled"],
            rrf_k=row["rrf_k"],
            weight_lexical=float(row["weight_lexical"]),
            weight_vector=float(row["weight_vector"]),
            lexical_engine=row["lexical_engine"],
            rebuild_job_id=rebuild_job_id,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

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
            default_strategy_id=cfg["default_strategy_id"],
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

    @router.put("/workspaces/{name}/chunking-config/engine")
    async def put_chunking_engine_endpoint(
        name: str,
        payload: EngineSpec,
        request: Request,
        confirm: bool = False,
    ) -> Response:
        """Bascule le moteur de chunking (`legacy` ↔ `structured`).

        - 204 si moteur déjà à la valeur demandée.
        - 200 + EngineResponse si bascule sans documents indexés.
        - 409 ``chunking_change_requires_reindex`` si bascule + docs > 0 sans
          ``confirm=true`` (réindexation complète requise).
        - 202 + JobResponse si bascule + docs > 0 + ``confirm=true``.
        - 404 si workspace inconnu.
        """
        from rag.services.jobs import apply_engine_change

        config_pool = _config_pool(request)
        result = await apply_engine_change(
            name=name, engine=payload.engine, confirm=confirm, config_pool=config_pool
        )

        if result == "no_change":
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        tag, body = result
        if tag == "updated":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=EngineResponse(
                    workspace_id=body["workspace_id"], engine=body["engine"]
                ).model_dump(mode="json"),
            )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=JobResponse(**body).model_dump(mode="json"),
        )

    @router.put("/workspaces/{name}/chunking-config/default-strategy")
    async def put_default_strategy_endpoint(
        name: str,
        payload: DefaultStrategySpec,
        request: Request,
        confirm: bool = False,
    ) -> Response:
        """Change la stratégie par défaut LIÉE PAR ID du workspace (spec §5).

        Même protocole que la bascule moteur : 204 (identique), 200 +
        DefaultStrategyResponse (0 doc), 409 ``chunking_change_requires_reindex``
        (docs > 0 sans confirm), 202 + JobResponse (confirm), 404 workspace,
        422 stratégie invisible pour le caller.
        """
        from rag.auth.owner import get_current_owner_id
        from rag.services.jobs import UnknownDefaultStrategyError, apply_default_strategy_change

        config_pool = _config_pool(request)
        owner_id = get_current_owner_id(request)
        try:
            result = await apply_default_strategy_change(
                name=name,
                strategy_id=payload.strategy_id,
                owner_id=owner_id,
                confirm=confirm,
                config_pool=config_pool,
            )
        except UnknownDefaultStrategyError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

        if result == "no_change":
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        tag, body = result
        if tag == "updated":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=DefaultStrategyResponse(
                    workspace_id=body["workspace_id"],
                    default_strategy_id=body["default_strategy_id"],
                ).model_dump(mode="json"),
            )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=JobResponse(**body).model_dump(mode="json"),
        )

    # ─── Webhooks sources ───────────────────────────────────────────────────

    @router.post(
        "/workspaces/{name}/sources/{source_name}/webhook/enable",
        response_model=WebhookEnableResponse,
    )
    async def enable_source_webhook(
        name: str, source_name: str, request: Request
    ) -> WebhookEnableResponse:
        from rag.services.source_webhooks import (
            WebhookAlreadyEnabledError,
            enable_webhook,
        )

        try:
            async with _config_pool(request).acquire() as conn:
                secret = await enable_webhook(
                    conn,
                    workspace_name=name,
                    source_name=source_name,
                    vault_svc=request.app.state.harpocrate_vaults_service,
                    client_provider=request.app.state.client_provider,
                )
        except WebhookAlreadyEnabledError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        public_url = str(request.app.state.settings.rag_public_url).rstrip("/")
        webhook_url = f"{public_url}/api/webhooks/git/{name}/{source_name}"
        return WebhookEnableResponse(
            source_name=source_name,
            webhook_url=webhook_url,
            secret=secret,
        )

    @router.post(
        "/workspaces/{name}/sources/{source_name}/webhook/disable",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def disable_source_webhook(name: str, source_name: str, request: Request) -> Response:
        from rag.services.source_webhooks import (
            WebhookNotEnabledError,
            disable_webhook,
        )

        try:
            async with _config_pool(request).acquire() as conn:
                await disable_webhook(
                    conn,
                    workspace_name=name,
                    source_name=source_name,
                    vault_svc=request.app.state.harpocrate_vaults_service,
                    client_provider=request.app.state.client_provider,
                )
        except WebhookNotEnabledError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/workspaces/{name}/sources/{source_name}/webhook/rotate-secret",
        response_model=dict,
    )
    async def rotate_source_webhook_secret(name: str, source_name: str, request: Request) -> dict:
        from rag.services.source_webhooks import (
            WebhookNotEnabledError,
            rotate_webhook_secret,
        )

        try:
            async with _config_pool(request).acquire() as conn:
                new_secret = await rotate_webhook_secret(
                    conn,
                    workspace_name=name,
                    source_name=source_name,
                    vault_svc=request.app.state.harpocrate_vaults_service,
                    client_provider=request.app.state.client_provider,
                )
        except WebhookNotEnabledError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        return {"secret": new_secret}

    return router
