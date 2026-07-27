from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.api.admin_chunking_strategies import _mapped_errors
from rag.auth.workspace_auth import OwnerAuthContext, require_apikey_owner
from rag.schemas.chunking_strategies import (
    ParserOut,
    RegionRouteOut,
    RoutesUpdate,
    StrategyCreate,
    StrategyDetailOut,
    StrategyDuplicate,
    StrategyOut,
    StrategyPatch,
    StrategyPromptOut,
    StrategyPromptsUpdate,
)
from rag.services import chunking_strategies as svc


@asynccontextmanager
async def _conn_mapped(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    """Acquiert une connexion ET applique le mapping d'erreurs métier→HTTP
    (le CM d'erreurs est synchrone : on le compose ici en un seul async with)."""
    async with pool.acquire() as conn:
        with _mapped_errors():
            yield conn


def _require_admin_scope(auth: OwnerAuthContext) -> None:
    """Garde d'écriture : les mutations de bibliothèque exigent le scope `admin`
    (même règle que les outils MCP de bibliothèque)."""
    if auth.scope != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin_scope_required")


def build_library_apikey_router() -> APIRouter:
    """Bibliothèque de stratégies de chunking exposée par CLÉ API (parité MCP↔REST).

    Owner-scopée sur le propriétaire de la clé (require_apikey_owner) : système
    (partagées, lecture seule) + les siennes. Lectures dès le scope `read` ;
    mutations réservées au scope `admin`. Réutilise le MÊME service et le MÊME
    mapping d'erreurs que le router admin — aucune logique dupliquée.
    """
    router = APIRouter(prefix="/api/library", tags=["workspace", "apikey"])

    def _pool(request: Request) -> asyncpg.Pool:
        return request.app.state.pools.config_pool  # type: ignore[no-any-return]

    @router.get("/parsers", response_model=list[ParserOut], summary="Lister les parsers de régions")
    async def list_parsers(
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> list[ParserOut]:
        async with _pool(request).acquire() as conn:
            return await svc.list_parsers(conn)

    @router.get(
        "/strategies", response_model=list[StrategyOut], summary="Lister mes stratégies"
    )
    async def list_strategies(
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> list[StrategyOut]:
        async with _pool(request).acquire() as conn:
            return await svc.list_strategies(conn, owner_id=auth.owner_id)

    @router.get(
        "/strategies/{strategy_id}",
        response_model=StrategyDetailOut,
        summary="Détail d'une stratégie",
    )
    async def get_strategy(
        strategy_id: UUID,
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> StrategyDetailOut:
        async with _conn_mapped(_pool(request)) as conn:
            return await svc.get_strategy(conn, owner_id=auth.owner_id, strategy_id=strategy_id)

    @router.post(
        "/strategies",
        response_model=StrategyDetailOut,
        status_code=201,
        summary="Créer une stratégie",
    )
    async def create_strategy(
        req: StrategyCreate,
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> StrategyDetailOut:
        _require_admin_scope(auth)
        async with _conn_mapped(_pool(request)) as conn:
            return await svc.create_strategy(conn, owner_id=auth.owner_id, req=req)

    @router.patch(
        "/strategies/{strategy_id}",
        response_model=StrategyDetailOut,
        summary="Modifier une stratégie",
    )
    async def patch_strategy(
        strategy_id: UUID,
        req: StrategyPatch,
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> StrategyDetailOut:
        _require_admin_scope(auth)
        async with _conn_mapped(_pool(request)) as conn:
            return await svc.patch_strategy(
                conn, owner_id=auth.owner_id, strategy_id=strategy_id, req=req
            )

    @router.delete(
        "/strategies/{strategy_id}", status_code=204, summary="Supprimer une stratégie"
    )
    async def delete_strategy(
        strategy_id: UUID,
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> Response:
        _require_admin_scope(auth)
        async with _conn_mapped(_pool(request)) as conn:
            await svc.delete_strategy(conn, owner_id=auth.owner_id, strategy_id=strategy_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/strategies/{strategy_id}/duplicate",
        response_model=StrategyDetailOut,
        status_code=201,
        summary="Dupliquer une stratégie",
    )
    async def duplicate_strategy(
        strategy_id: UUID,
        req: StrategyDuplicate,
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> StrategyDetailOut:
        _require_admin_scope(auth)
        async with _conn_mapped(_pool(request)) as conn:
            return await svc.duplicate_strategy(
                conn, owner_id=auth.owner_id, source_id=strategy_id, label=req.label
            )

    @router.put(
        "/strategies/{strategy_id}/prompts",
        response_model=list[StrategyPromptOut],
        summary="Lier des prompts à une stratégie",
    )
    async def set_prompts(
        strategy_id: UUID,
        req: StrategyPromptsUpdate,
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> list[StrategyPromptOut]:
        _require_admin_scope(auth)
        async with _conn_mapped(_pool(request)) as conn:
            return await svc.set_strategy_prompts(
                conn, owner_id=auth.owner_id, strategy_id=strategy_id, prompts=req.prompts
            )

    @router.put(
        "/strategies/{strategy_id}/routes",
        response_model=list[RegionRouteOut],
        summary="Router les régions d'une stratégie",
    )
    async def set_routes(
        strategy_id: UUID,
        req: RoutesUpdate,
        request: Request,
        auth: OwnerAuthContext = Depends(require_apikey_owner),  # noqa: B008
    ) -> list[RegionRouteOut]:
        _require_admin_scope(auth)
        async with _conn_mapped(_pool(request)) as conn:
            return await svc.set_region_routes(
                conn, owner_id=auth.owner_id, strategy_id=strategy_id, routes=req.routes
            )

    return router
