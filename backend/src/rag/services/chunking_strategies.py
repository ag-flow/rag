from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.indexer.chunking.region_registry import available_parsers
from rag.indexer.chunking.structured_factory import validate_strategy_spec
from rag.schemas.chunking_strategies import (
    ParserOut,
    RegionRouteOut,
    RegionRouteSpec,
    StrategyCreate,
    StrategyDetailOut,
    StrategyOut,
    StrategyPatch,
)
from rag.schemas.slug import slugify

log = structlog.get_logger(__name__)


class StrategyNotFoundError(Exception):
    """Stratégie inexistante ou invisible pour cet utilisateur."""


class StrategyImmutableError(Exception):
    """Stratégie système : visible de tous, ni éditable ni supprimable."""


class StrategySlugConflictError(Exception):
    """Le slug dérivé du label entre en collision dans la bibliothèque."""


class InvalidStrategyError(Exception):
    """Spec invalide : algo/params/parser incohérents ou label sans slug."""


class StrategyInUseError(Exception):
    """Suppression refusée : la stratégie est référencée (spec §4)."""

    def __init__(self, *, used_by_routes: int, used_by_categories: int) -> None:
        self.used_by_routes = used_by_routes
        self.used_by_categories = used_by_categories
        super().__init__(
            f"stratégie utilisée par {used_by_routes} route(s) et {used_by_categories} catégorie(s)"
        )


# Portée bibliothèque : stratégies système + celles de l'utilisateur — les
# overrides par workspace (legacy, workspace_id NOT NULL) n'en font pas partie.
# Fragments SQL statiques (aucun input utilisateur) — les noqa S608 couvrent
# uniquement leur interpolation.
_OUT_COLUMNS = """
    s.id, s.label, s.slug, s.algo, s.params, s.parser_slug,
    (s.owner_id IS NULL) AS is_system, s.created_at, s.updated_at,
    (SELECT count(*) FROM chunking_strategy_region_routes r
       WHERE r.target_strategy_id = s.id)::int AS used_by_routes,
    (CASE WHEN s.owner_id IS NULL THEN
       (SELECT count(*) FROM chunking_category_strategies c WHERE c.strategy_name = s.slug)
     ELSE 0 END)::int AS used_by_categories
"""
_VISIBLE = "s.workspace_id IS NULL AND (s.owner_id IS NULL OR s.owner_id = $1)"


def _to_out(row: asyncpg.Record) -> StrategyOut:
    data = dict(row)
    if isinstance(data["params"], str):
        data["params"] = json.loads(data["params"])
    return StrategyOut.model_validate(data)


def _derive_slug(label: str) -> str:
    slug = slugify(label)
    if not slug:
        raise InvalidStrategyError(f"aucun slug dérivable du label {label!r}")
    return slug


def _validate_spec(algo: str, params: dict[str, Any], parser_slug: str | None) -> None:
    if parser_slug is not None and parser_slug not in available_parsers():
        raise InvalidStrategyError(f"parser inconnu : {parser_slug!r}")
    try:
        validate_strategy_spec(algo=algo, params=params, parser_slug=parser_slug)
    except ValueError as exc:
        raise InvalidStrategyError(str(exc)) from exc


async def list_parsers(conn: asyncpg.Connection) -> list[ParserOut]:
    rows = await conn.fetch("SELECT slug, label FROM chunking_parsers ORDER BY slug")
    return [ParserOut.model_validate(dict(r)) for r in rows]


async def list_strategies(conn: asyncpg.Connection, *, owner_id: str) -> list[StrategyOut]:
    rows = await conn.fetch(
        f"SELECT {_OUT_COLUMNS} FROM chunking_strategies s WHERE {_VISIBLE} "  # noqa: S608
        "ORDER BY is_system DESC, s.label",
        owner_id,
    )
    return [_to_out(r) for r in rows]


async def get_strategy(
    conn: asyncpg.Connection, *, owner_id: str, strategy_id: UUID
) -> StrategyDetailOut:
    row = await conn.fetchrow(
        f"SELECT {_OUT_COLUMNS} FROM chunking_strategies s "  # noqa: S608
        f"WHERE {_VISIBLE} AND s.id = $2",
        owner_id,
        strategy_id,
    )
    if row is None:
        raise StrategyNotFoundError(str(strategy_id))
    routes = await _fetch_routes(conn, strategy_id)
    return StrategyDetailOut(**_to_out(row).model_dump(), routes=routes)


async def _fetch_routes(conn: asyncpg.Connection, strategy_id: UUID) -> list[RegionRouteOut]:
    rows = await conn.fetch(
        "SELECT region_type, qualifier, target_strategy_id, atomic, overflow_policy "
        "FROM chunking_strategy_region_routes WHERE strategy_id = $1 "
        "ORDER BY region_type, qualifier",
        strategy_id,
    )
    return [RegionRouteOut.model_validate(dict(r)) for r in rows]


async def create_strategy(
    conn: asyncpg.Connection, *, owner_id: str, req: StrategyCreate
) -> StrategyDetailOut:
    _validate_spec(req.algo, req.params, req.parser_slug)
    slug = _derive_slug(req.label)
    try:
        strategy_id = await conn.fetchval(
            "INSERT INTO chunking_strategies (owner_id, label, slug, algo, params, parser_slug) "
            "VALUES ($1, $2, $3, $4, $5::jsonb, $6) RETURNING id",
            owner_id,
            req.label,
            slug,
            req.algo,
            json.dumps(req.params),
            req.parser_slug,
        )
    except asyncpg.UniqueViolationError as exc:
        raise StrategySlugConflictError(slug) from exc
    log.info("chunking_strategy.created", strategy_id=str(strategy_id), slug=slug)
    return await get_strategy(conn, owner_id=owner_id, strategy_id=strategy_id)


async def _fetch_owned(
    conn: asyncpg.Connection, *, owner_id: str, strategy_id: UUID
) -> asyncpg.Record:
    """Charge une stratégie pour modification : la sienne uniquement.

    Système → immutable ; inexistante, d'un autre user ou override workspace
    → introuvable (pas de fuite d'existence entre bibliothèques).
    """
    row = await conn.fetchrow(
        "SELECT id, owner_id, label, slug, algo, params, parser_slug "  # noqa: S608
        "FROM chunking_strategies s "
        f"WHERE {_VISIBLE} AND s.id = $2 FOR UPDATE",
        owner_id,
        strategy_id,
    )
    if row is None:
        raise StrategyNotFoundError(str(strategy_id))
    if row["owner_id"] is None:
        raise StrategyImmutableError(str(strategy_id))
    return row


async def patch_strategy(
    conn: asyncpg.Connection, *, owner_id: str, strategy_id: UUID, req: StrategyPatch
) -> StrategyDetailOut:
    async with conn.transaction():
        row = await _fetch_owned(conn, owner_id=owner_id, strategy_id=strategy_id)
        label = req.label if req.label is not None else row["label"]
        params = req.params if req.params is not None else _params_of(row)
        parser_slug = (
            req.parser_slug if "parser_slug" in req.model_fields_set else row["parser_slug"]
        )
        _validate_spec(row["algo"], params, parser_slug)
        slug = _derive_slug(label)
        try:
            await conn.execute(
                "UPDATE chunking_strategies SET label=$2, slug=$3, params=$4::jsonb, "
                "parser_slug=$5, updated_at=now() WHERE id=$1",
                strategy_id,
                label,
                slug,
                json.dumps(params),
                parser_slug,
            )
        except asyncpg.UniqueViolationError as exc:
            raise StrategySlugConflictError(slug) from exc
    return await get_strategy(conn, owner_id=owner_id, strategy_id=strategy_id)


def _params_of(row: asyncpg.Record) -> dict[str, Any]:
    params = row["params"]
    return json.loads(params) if isinstance(params, str) else dict(params)


async def delete_strategy(conn: asyncpg.Connection, *, owner_id: str, strategy_id: UUID) -> None:
    async with conn.transaction():
        await _fetch_owned(conn, owner_id=owner_id, strategy_id=strategy_id)
        used_by_routes = await conn.fetchval(
            "SELECT count(*) FROM chunking_strategy_region_routes "
            "WHERE target_strategy_id = $1 AND strategy_id <> $1",
            strategy_id,
        )
        if int(used_by_routes) > 0:
            raise StrategyInUseError(used_by_routes=int(used_by_routes), used_by_categories=0)
        try:
            await conn.execute("DELETE FROM chunking_strategies WHERE id = $1", strategy_id)
        except asyncpg.ForeignKeyViolationError as exc:  # course avec une route
            raise StrategyInUseError(used_by_routes=1, used_by_categories=0) from exc
    log.info("chunking_strategy.deleted", strategy_id=str(strategy_id))


async def duplicate_strategy(
    conn: asyncpg.Connection, *, owner_id: str, source_id: UUID, label: str
) -> StrategyDetailOut:
    """Copie une stratégie visible (système ou la sienne) : params + routes."""
    slug = _derive_slug(label)
    async with conn.transaction():
        source = await conn.fetchrow(
            "SELECT s.algo, s.params, s.parser_slug FROM chunking_strategies s "  # noqa: S608
            f"WHERE {_VISIBLE} AND s.id = $2",
            owner_id,
            source_id,
        )
        if source is None:
            raise StrategyNotFoundError(str(source_id))
        try:
            new_id = await conn.fetchval(
                "INSERT INTO chunking_strategies "
                "(owner_id, label, slug, algo, params, parser_slug) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6) RETURNING id",
                owner_id,
                label,
                slug,
                source["algo"],
                json.dumps(_params_of(source)),
                source["parser_slug"],
            )
        except asyncpg.UniqueViolationError as exc:
            raise StrategySlugConflictError(slug) from exc
        await conn.execute(
            "INSERT INTO chunking_strategy_region_routes "
            "(strategy_id, region_type, qualifier, target_strategy_id, atomic, overflow_policy) "
            "SELECT $2, region_type, qualifier, target_strategy_id, atomic, overflow_policy "
            "FROM chunking_strategy_region_routes WHERE strategy_id = $1",
            source_id,
            new_id,
        )
    log.info("chunking_strategy.duplicated", source_id=str(source_id), strategy_id=str(new_id))
    return await get_strategy(conn, owner_id=owner_id, strategy_id=new_id)


async def set_region_routes(
    conn: asyncpg.Connection,
    *,
    owner_id: str,
    strategy_id: UUID,
    routes: list[RegionRouteSpec],
) -> list[RegionRouteOut]:
    """Remplace le jeu complet de routes d'une stratégie de l'utilisateur.

    Chaque cible doit être une stratégie visible (système ou la sienne) —
    le binding reste par id une fois la route écrite (règle d'or, spec §4).
    """
    async with conn.transaction():
        row = await _fetch_owned(conn, owner_id=owner_id, strategy_id=strategy_id)
        if row["parser_slug"] is None:
            raise InvalidStrategyError("routes de régions sans parser_slug sur la stratégie")
        await _check_targets_visible(conn, owner_id=owner_id, routes=routes)
        await conn.execute(
            "DELETE FROM chunking_strategy_region_routes WHERE strategy_id = $1", strategy_id
        )
        await conn.executemany(
            "INSERT INTO chunking_strategy_region_routes "
            "(strategy_id, region_type, qualifier, target_strategy_id, atomic, overflow_policy) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            [
                (
                    strategy_id,
                    r.region_type,
                    r.qualifier,
                    r.target_strategy_id,
                    r.atomic,
                    r.overflow_policy,
                )
                for r in routes
            ],
        )
    log.info("chunking_strategy.routes_set", strategy_id=str(strategy_id), routes=len(routes))
    return await _fetch_routes(conn, strategy_id)


async def _check_targets_visible(
    conn: asyncpg.Connection, *, owner_id: str, routes: list[RegionRouteSpec]
) -> None:
    wanted = {r.target_strategy_id for r in routes if r.target_strategy_id is not None}
    if not wanted:
        return
    rows = await conn.fetch(
        f"SELECT s.id FROM chunking_strategies s "  # noqa: S608
        f"WHERE {_VISIBLE} AND s.id = ANY($2::uuid[])",
        owner_id,
        list(wanted),
    )
    missing = wanted - {r["id"] for r in rows}
    if missing:
        raise InvalidStrategyError(
            f"cible(s) de route introuvable(s) : {sorted(str(m) for m in missing)}"
        )
