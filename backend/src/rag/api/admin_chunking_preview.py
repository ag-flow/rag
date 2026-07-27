from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.schemas.chunking_preview import (
    CompareRequest,
    CompareResult,
    PreviewRequest,
    PreviewResult,
)
from rag.services.chunking_preview import (
    PreviewStrategyNotFoundError,
    compare_strategies,
    preview_strategy,
)

log = structlog.get_logger(__name__)


def build_chunking_preview_router() -> APIRouter:
    """Preview de découpage sans réindexation (spec chunking §6 item 7, S5.2).

    Opérations PURES : aucun embedding, aucune écriture pgvector, aucun job.
    """
    router = APIRouter(
        prefix="/api/admin/chunking",
        tags=["chunking-preview"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    def _pool(request: Request) -> asyncpg.Pool:
        return request.app.state.pools.config_pool  # type: ignore[no-any-return]

    @router.post("/preview", response_model=PreviewResult)
    async def preview(req: PreviewRequest, request: Request) -> PreviewResult:
        owner_id = get_current_owner_id(request)
        try:
            return await preview_strategy(
                _pool(request),
                owner_id=owner_id,
                strategy_id=req.strategy_id,
                content=req.content,
                workspace_name=req.workspace_name,
                run_prompts=req.run_prompts,
            )
        except PreviewStrategyNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "stratégie introuvable") from exc
        except ChunkTooLargeError as exc:
            # keep_whole face au plafond dur : feedback utile en itération.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    @router.post("/preview/compare", response_model=CompareResult)
    async def compare(req: CompareRequest, request: Request) -> CompareResult:
        owner_id = get_current_owner_id(request)
        try:
            return await compare_strategies(
                _pool(request),
                owner_id=owner_id,
                content=req.content,
                strategy_a=req.strategy_a,
                strategy_b=req.strategy_b,
            )
        except PreviewStrategyNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "stratégie introuvable") from exc
        except ChunkTooLargeError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return router
