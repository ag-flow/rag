from __future__ import annotations

import asyncio
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.playground import (
    LlmConfigCreate,
    LlmConfigOut,
    LlmConfigPatch,
    PlaygroundChatRequest,
    PlaygroundChatResponse,
)

log = structlog.get_logger(__name__)

# ─── CRUD LLM configs (admin) ─────────────────────────────────────────────────

router_admin = APIRouter(
    prefix="/api/admin/workspaces/{workspace_name}/llm-configs",
    tags=["playground-admin"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


@router_admin.get("", response_model=list[LlmConfigOut])
async def list_configs(workspace_name: str, request: Request) -> list[LlmConfigOut]:
    from rag.services.llm_configs import list_llm_configs
    async with _pool(request).acquire() as conn:
        return await list_llm_configs(conn, workspace_name=workspace_name)


@router_admin.post("", response_model=LlmConfigOut, status_code=201)
async def create_config(
    workspace_name: str, body: LlmConfigCreate, request: Request
) -> LlmConfigOut:
    from rag.services.llm_configs import create_llm_config
    async with _pool(request).acquire() as conn:
        try:
            return await create_llm_config(conn, workspace_name=workspace_name, req=body)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status.HTTP_409_CONFLICT, "already exists") from exc
            raise


@router_admin.patch("/{config_id}", response_model=LlmConfigOut)
async def patch_config(
    workspace_name: str, config_id: UUID, body: LlmConfigPatch, request: Request
) -> LlmConfigOut:
    from rag.services.llm_configs import patch_llm_config
    async with _pool(request).acquire() as conn:
        result = await patch_llm_config(
            conn, workspace_name=workspace_name, config_id=str(config_id), req=body
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "llm config not found")
    return result


@router_admin.delete("/{config_id}", status_code=204)
async def delete_config(
    workspace_name: str, config_id: UUID, request: Request
) -> Response:
    from rag.services.llm_configs import delete_llm_config
    async with _pool(request).acquire() as conn:
        deleted = await delete_llm_config(
            conn, workspace_name=workspace_name, config_id=str(config_id)
        )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "llm config not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Chat (rag-admin + rag-viewer) ────────────────────────────────────────────

router_chat = APIRouter(
    prefix="/api/workspaces",
    tags=["playground-chat"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


@router_chat.post("/{workspace_name}/playground/chat", response_model=PlaygroundChatResponse)
async def playground_chat(
    workspace_name: str,
    body: PlaygroundChatRequest,
    request: Request,
) -> PlaygroundChatResponse:
    """Chat RAG-ancré : embed → vector_search → LLM."""
    from rag.db.workspace_search import vector_search
    from rag.indexer.providers.factory import make_provider
    from rag.secrets.refs import is_vault_ref, parse_ref
    from rag.services.llm_clients import build_prompt, call_llm
    from rag.services.llm_configs import get_llm_config_for_chat

    config_pool: asyncpg.Pool = _pool(request)
    pool_registry = request.app.state.pools
    vault_svc = request.app.state.harpocrate_vaults_service
    client_provider = request.app.state.client_provider

    async def _resolve_harpo(harpo_path: str) -> str | None:
        if not is_vault_ref(harpo_path):
            return None
        vault_name, secret_path = parse_ref(harpo_path)
        async with config_pool.acquire() as conn:
            vault = await vault_svc.get_by_name(conn, vault_name)
        if vault is None:
            return None
        client = await client_provider.get_client(vault.api_key_id)
        return await asyncio.to_thread(client.get_secret, secret_path)

    # 1. Workspace + indexer config
    async with config_pool.acquire() as conn:
        ws_row = await conn.fetchrow(
            """
            SELECT w.rag_cnx, w.name AS ws_name,
                   ic.provider AS idx_provider, ic.model AS idx_model,
                   ic.api_key_ref AS idx_api_key_ref, ic.base_url AS idx_base_url
            FROM workspaces w
            JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.name = $1
            """,
            workspace_name,
        )
        if ws_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace not found")

        # 2. LLM config
        llm_cfg = await get_llm_config_for_chat(
            conn,
            workspace_name=workspace_name,
            provider=body.llm.provider,
            model=body.llm.model,
        )

    if llm_cfg is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"LLM {body.llm.provider}/{body.llm.model} not configured or disabled",
        )

    # 3. Embed la requête
    indexer_api_key: str | None = None
    if ws_row["idx_api_key_ref"]:
        indexer_api_key = await _resolve_harpo(ws_row["idx_api_key_ref"])

    embedding_provider = make_provider(
        provider=ws_row["idx_provider"],
        model=ws_row["idx_model"],
        api_key=indexer_api_key,
        base_url=ws_row["idx_base_url"],
    )
    query_vec = await embedding_provider.embed_query(body.message)

    # 4. Recherche vectorielle
    ws_pool = await pool_registry.get_workspace_pool(workspace_name, ws_row["rag_cnx"])
    raw_hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=body.top_k,
        min_score=body.min_score,
        workspace_name=workspace_name,
        indexer_used=f"{ws_row['idx_provider']}/{ws_row['idx_model']}",
    )

    chunks = [
        {"path": h.path, "chunk_index": h.chunk_index, "content": h.content, "score": h.score}
        for h in raw_hits
    ]

    # 5. Appel LLM
    llm_api_key: str | None = None
    if llm_cfg.get("api_key_ref"):
        llm_api_key = await _resolve_harpo(llm_cfg["api_key_ref"])

    system_prompt, messages = build_prompt(
        chunks=chunks,
        history=[{"role": m.role, "content": m.content} for m in body.history],
        message=body.message,
    )
    llm_result = await call_llm(
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        api_key=llm_api_key,
        base_url=llm_cfg.get("base_url"),
        system_prompt=system_prompt,
        messages=messages,
    )

    log.info(
        "playground.chat",
        workspace=workspace_name,
        provider=llm_cfg["provider"],
        model=llm_cfg["model"],
        chunks=len(chunks),
    )

    return PlaygroundChatResponse(
        message=body.message,
        answer=llm_result["answer"],
        chunks=chunks,
        usage=llm_result["usage"],
    )
