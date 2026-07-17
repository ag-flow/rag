from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.chunking_strategies import RegionRouteSpec, StrategyCreate, StrategyPatch
from rag.services import chunking_strategies as svc

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "1" * 64
OWNER_B = "2" * 64


async def _conn(session_pool: asyncpg.Pool) -> asyncpg.Connection:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    return await session_pool.acquire()


@pytest.mark.asyncio
async def test_list_scopes_system_plus_mine(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        mine = await svc.create_strategy(
            conn, owner_id=OWNER_A, req=StrategyCreate(label="Prose A (svc)", algo="prose")
        )
        await svc.create_strategy(
            conn, owner_id=OWNER_B, req=StrategyCreate(label="Prose B (svc)", algo="prose")
        )
        listed = await svc.list_strategies(conn, owner_id=OWNER_A)
        slugs = {s.slug for s in listed}
        assert mine.slug in slugs
        assert "markdown-deep" in slugs  # système visible
        assert "prose-b-svc" not in slugs  # bibliothèque d'un autre user invisible
        assert mine.is_system is False
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_system_strategy_immutable(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        system = next(s for s in await svc.list_strategies(conn, owner_id=OWNER_A) if s.is_system)
        with pytest.raises(svc.StrategyImmutableError):
            await svc.patch_strategy(
                conn, owner_id=OWNER_A, strategy_id=system.id, req=StrategyPatch(label="Pirate")
            )
        with pytest.raises(svc.StrategyImmutableError):
            await svc.delete_strategy(conn, owner_id=OWNER_A, strategy_id=system.id)
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_rename_rederives_slug_and_detects_collision(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        s1 = await svc.create_strategy(
            conn, owner_id=OWNER_A, req=StrategyCreate(label="Rename un", algo="prose")
        )
        await svc.create_strategy(
            conn, owner_id=OWNER_A, req=StrategyCreate(label="Rename deux", algo="prose")
        )
        renamed = await svc.patch_strategy(
            conn, owner_id=OWNER_A, strategy_id=s1.id, req=StrategyPatch(label="Rename Trois !")
        )
        assert (renamed.label, renamed.slug) == ("Rename Trois !", "rename-trois")
        with pytest.raises(svc.StrategySlugConflictError):
            await svc.patch_strategy(
                conn,
                owner_id=OWNER_A,
                strategy_id=s1.id,
                req=StrategyPatch(label="Rename  Deux"),
            )
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_duplicate_copies_params_and_routes(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        target = await svc.create_strategy(
            conn, owner_id=OWNER_A, req=StrategyCreate(label="Cible mermaid", algo="prose")
        )
        source = await svc.create_strategy(
            conn,
            owner_id=OWNER_A,
            req=StrategyCreate(
                label="Source régions",
                algo="prose",
                params={"child_target_tokens": 256},
                parser_slug="markdown",
            ),
        )
        await svc.set_region_routes(
            conn,
            owner_id=OWNER_A,
            strategy_id=source.id,
            routes=[
                RegionRouteSpec(
                    region_type="code_fence",
                    qualifier="mermaid",
                    target_strategy_id=target.id,
                )
            ],
        )
        copy = await svc.duplicate_strategy(
            conn, owner_id=OWNER_A, source_id=source.id, label="Copie régions"
        )
        assert copy.slug == "copie-regions"
        assert copy.params == {"child_target_tokens": 256}
        assert copy.parser_slug == "markdown"
        assert [(r.region_type, r.qualifier, r.target_strategy_id) for r in copy.routes] == [
            ("code_fence", "mermaid", target.id)
        ]
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_delete_refused_when_targeted_by_route(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        target = await svc.create_strategy(
            conn, owner_id=OWNER_A, req=StrategyCreate(label="Cible protégée", algo="prose")
        )
        router = await svc.create_strategy(
            conn,
            owner_id=OWNER_A,
            req=StrategyCreate(label="Routeur garde", algo="prose", parser_slug="markdown"),
        )
        await svc.set_region_routes(
            conn,
            owner_id=OWNER_A,
            strategy_id=router.id,
            routes=[RegionRouteSpec(region_type="table", target_strategy_id=target.id)],
        )
        with pytest.raises(svc.StrategyInUseError):
            await svc.delete_strategy(conn, owner_id=OWNER_A, strategy_id=target.id)
        # le routeur, lui, se supprime (ses routes partent en CASCADE)
        await svc.delete_strategy(conn, owner_id=OWNER_A, strategy_id=router.id)
        await svc.delete_strategy(conn, owner_id=OWNER_A, strategy_id=target.id)
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_routes_require_parser_and_visible_targets(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        no_parser = await svc.create_strategy(
            conn, owner_id=OWNER_A, req=StrategyCreate(label="Sans parser", algo="prose")
        )
        with pytest.raises(svc.InvalidStrategyError):
            await svc.set_region_routes(
                conn,
                owner_id=OWNER_A,
                strategy_id=no_parser.id,
                routes=[RegionRouteSpec(region_type="table", atomic=True)],
            )
        foreign = await svc.create_strategy(
            conn, owner_id=OWNER_B, req=StrategyCreate(label="Cible étrangère", algo="prose")
        )
        routed = await svc.create_strategy(
            conn,
            owner_id=OWNER_A,
            req=StrategyCreate(label="Routes visibilité", algo="prose", parser_slug="markdown"),
        )
        with pytest.raises(svc.InvalidStrategyError):
            await svc.set_region_routes(
                conn,
                owner_id=OWNER_A,
                strategy_id=routed.id,
                routes=[RegionRouteSpec(region_type="table", target_strategy_id=foreign.id)],
            )
    finally:
        await session_pool.release(conn)


@pytest.mark.asyncio
async def test_create_rejects_invalid_spec(session_pool: asyncpg.Pool) -> None:
    conn = await _conn(session_pool)
    try:
        with pytest.raises(svc.InvalidStrategyError):
            await svc.create_strategy(
                conn,
                owner_id=OWNER_A,
                req=StrategyCreate(label="Table à parser", algo="table", parser_slug="markdown"),
            )
        with pytest.raises(svc.InvalidStrategyError):
            await svc.create_strategy(
                conn,
                owner_id=OWNER_A,
                req=StrategyCreate(label="Params inconnus", algo="prose", params={"bogus": 1}),
            )
        with pytest.raises(svc.InvalidStrategyError):
            await svc.create_strategy(
                conn, owner_id=OWNER_A, req=StrategyCreate(label="!!!", algo="prose")
            )
    finally:
        await session_pool.release(conn)
