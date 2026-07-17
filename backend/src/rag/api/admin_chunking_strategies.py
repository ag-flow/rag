from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.chunking_strategies import (
    ParserOut,
    RegionRouteOut,
    RoutesUpdate,
    StrategyCreate,
    StrategyDetailOut,
    StrategyDuplicate,
    StrategyOut,
    StrategyPatch,
)
from rag.services import chunking_strategies as svc

log = structlog.get_logger(__name__)


def build_chunking_strategies_router() -> APIRouter:
    """Bibliothèque de stratégies de chunking (spec chunking §4, F3).

    Portée : stratégies système (owner NULL, lecture seule) + celles de
    l'utilisateur courant. Le slug est toujours dérivé du label côté serveur.
    """
    router = APIRouter(
        prefix="/api/admin/chunking",
        tags=["chunking-strategies"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    def _pool(request: Request) -> asyncpg.Pool:
        return request.app.state.pools.config_pool  # type: ignore[no-any-return]

    @router.get("/parsers", response_model=list[ParserOut])
    async def list_parsers(request: Request) -> list[ParserOut]:
        async with _pool(request).acquire() as conn:
            return await svc.list_parsers(conn)

    @router.get("/strategies", response_model=list[StrategyOut])
    async def list_strategies(request: Request) -> list[StrategyOut]:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            return await svc.list_strategies(conn, owner_id=owner_id)

    @router.post("/strategies", response_model=StrategyDetailOut, status_code=201)
    async def create_strategy(req: StrategyCreate, request: Request) -> StrategyDetailOut:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            with _mapped_errors():
                return await svc.create_strategy(conn, owner_id=owner_id, req=req)

    @router.get("/strategies/{strategy_id}", response_model=StrategyDetailOut)
    async def get_strategy(strategy_id: UUID, request: Request) -> StrategyDetailOut:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            with _mapped_errors():
                return await svc.get_strategy(conn, owner_id=owner_id, strategy_id=strategy_id)

    @router.patch("/strategies/{strategy_id}", response_model=StrategyDetailOut)
    async def patch_strategy(
        strategy_id: UUID, req: StrategyPatch, request: Request
    ) -> StrategyDetailOut:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            with _mapped_errors():
                return await svc.patch_strategy(
                    conn, owner_id=owner_id, strategy_id=strategy_id, req=req
                )

    @router.delete("/strategies/{strategy_id}", status_code=204)
    async def delete_strategy(strategy_id: UUID, request: Request) -> Response:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            with _mapped_errors():
                await svc.delete_strategy(conn, owner_id=owner_id, strategy_id=strategy_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post(
        "/strategies/{strategy_id}/duplicate",
        response_model=StrategyDetailOut,
        status_code=201,
    )
    async def duplicate_strategy(
        strategy_id: UUID, req: StrategyDuplicate, request: Request
    ) -> StrategyDetailOut:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            with _mapped_errors():
                return await svc.duplicate_strategy(
                    conn, owner_id=owner_id, source_id=strategy_id, label=req.label
                )

    @router.put("/strategies/{strategy_id}/routes", response_model=list[RegionRouteOut])
    async def set_routes(
        strategy_id: UUID, req: RoutesUpdate, request: Request
    ) -> list[RegionRouteOut]:
        owner_id = get_current_owner_id(request)
        async with _pool(request).acquire() as conn:
            with _mapped_errors():
                return await svc.set_region_routes(
                    conn, owner_id=owner_id, strategy_id=strategy_id, routes=req.routes
                )

    return router


@contextmanager
def _mapped_errors() -> Iterator[None]:
    """Traduit les erreurs métier du service en réponses HTTP."""
    try:
        yield
    except svc.StrategyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stratégie introuvable") from exc
    except svc.StrategyImmutableError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "stratégie système non modifiable") from exc
    except svc.StrategySlugConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"slug déjà utilisé : {exc}") from exc
    except svc.StrategyInUseError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except svc.InvalidStrategyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
