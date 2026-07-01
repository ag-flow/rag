from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.db.index_keys import get_document_sections, get_path_chunks, list_paths_aggregate
from rag.db.path_strategies import get_all_for_workspace, upsert_strategy
from rag.db.pool import WorkspacePoolRegistry
from rag.schemas.index_keys import (
    ChunkEntry,
    DocumentViewResponse,
    EmbedChunkEntry,
    IndexKeysResponse,
    PathDetailResponse,
    PathStrategyEntry,
    SectionEntry,
    StrategyPatchRequest,
    VersionGroup,
)


def build_index_keys_router() -> APIRouter:
    router = APIRouter(
        tags=["admin"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    async def _workspace_context(
        config_pool: asyncpg.Pool,
        name: str,
    ) -> tuple[UUID, str]:
        """Retourne (workspace_id, rag_cnx) ou lève 404."""
        row = await config_pool.fetchrow(
            "SELECT id, rag_cnx FROM workspaces WHERE name=$1", name
        )
        if row is None:
            raise HTTPException(status_code=404, detail="workspace_not_found")
        return row["id"], row["rag_cnx"]

    @router.get(
        "/workspaces/{name}/document-view",
        response_model=DocumentViewResponse,
    )
    async def get_document_view(
        name: str,
        path: str,
        request: Request,
    ) -> DocumentViewResponse:
        registry: WorkspacePoolRegistry = request.app.state.pools
        config_pool: asyncpg.Pool = registry.config_pool
        _, rag_cnx = await _workspace_context(config_pool, name)
        ws_pool = await registry.get_workspace_pool(name, rag_cnx)
        sections_raw, is_legacy = await get_document_sections(ws_pool, path)

        sections = [
            SectionEntry(
                section_index=s["section_index"],
                section_key=s["section_key"],
                content=s["content"],
                metadata=s["metadata"],
                chunks=[
                    EmbedChunkEntry(
                        chunk_index=c["chunk_index"],
                        embed_text=c["embed_text"],
                        metadata=c["metadata"],
                    )
                    for c in s["chunks"]
                ],
            )
            for s in sections_raw
        ]
        return DocumentViewResponse(path=path, sections=sections, is_legacy=is_legacy)

    @router.get("/workspaces/{name}/index-keys", response_model=IndexKeysResponse)
    async def get_index_keys(name: str, request: Request) -> IndexKeysResponse:
        registry: WorkspacePoolRegistry = request.app.state.pools
        config_pool: asyncpg.Pool = registry.config_pool
        ws_id, rag_cnx = await _workspace_context(config_pool, name)

        path_rows = await config_pool.fetch(
            "SELECT path FROM indexed_documents WHERE workspace_id=$1 ORDER BY path",
            ws_id,
        )
        paths = [r["path"] for r in path_rows]
        strategies = await get_all_for_workspace(config_pool, ws_id)
        ws_pool = await registry.get_workspace_pool(name, rag_cnx)
        agg = await list_paths_aggregate(ws_pool, paths)

        entries = [
            PathStrategyEntry(
                path=p,
                strategy=strategies[p]["strategy"] if p in strategies else "replace",
                updated_by=strategies[p]["updated_by"] if p in strategies else "ui",
                chunk_count=agg.get(p, {}).get("chunk_count", 0),
                version_count=agg.get(p, {}).get("version_count", 0),
                last_indexed_at=agg.get(p, {}).get("last_indexed_at"),
            )
            for p in paths
        ]
        return IndexKeysResponse(paths=entries, total=len(entries))

    @router.get(
        "/workspaces/{name}/index-keys/{path:path}",
        response_model=PathDetailResponse,
    )
    async def get_index_key_detail(
        name: str, path: str, request: Request
    ) -> PathDetailResponse:
        registry: WorkspacePoolRegistry = request.app.state.pools
        config_pool: asyncpg.Pool = registry.config_pool
        ws_id, rag_cnx = await _workspace_context(config_pool, name)

        strategies = await get_all_for_workspace(config_pool, ws_id)
        strat = strategies.get(path)
        ws_pool = await registry.get_workspace_pool(name, rag_cnx)
        chunks_raw = await get_path_chunks(ws_pool, path)

        by_version: dict[datetime, list[ChunkEntry]] = defaultdict(list)
        for c in chunks_raw:
            by_version[c["indexed_at"]].append(
                ChunkEntry(
                    chunk_index=c["chunk_index"],
                    content=c["content"],
                    metadata=c["metadata"],
                    indexed_at=c["indexed_at"],
                )
            )

        versions = [
            VersionGroup(indexed_at=ts, chunks=chunks_list)
            for ts, chunks_list in sorted(by_version.items(), reverse=True)
        ]
        return PathDetailResponse(
            path=path,
            strategy=strat["strategy"] if strat else "replace",
            updated_by=strat["updated_by"] if strat else "ui",
            versions=versions,
        )

    @router.patch(
        "/workspaces/{name}/index-keys/{path:path}/strategy",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def patch_index_key_strategy(
        name: str,
        path: str,
        payload: StrategyPatchRequest,
        request: Request,
    ) -> Response:
        registry: WorkspacePoolRegistry = request.app.state.pools
        config_pool: asyncpg.Pool = registry.config_pool
        ws_id, _ = await _workspace_context(config_pool, name)
        await upsert_strategy(config_pool, ws_id, path, payload.strategy, "ui")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
