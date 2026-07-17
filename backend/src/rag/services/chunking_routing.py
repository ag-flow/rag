from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from rag.indexer.chunking.region_routes import RegionRoute
from rag.indexer.chunking.resolution import RoutingConfig, merge_maps
from rag.indexer.chunking.structured import StructuredChunkerProtocol
from rag.indexer.chunking.structured_factory import make_structured_chunker
from rag.indexer.chunking.tokens import TokenEstimator

# Fragment SQL statique (aucun input utilisateur) — les noqa S608 ci-dessous
# couvrent uniquement son interpolation.
_STRATEGY_COLUMNS = "id, algo, params, parser_slug"


@dataclass(frozen=True)
class StrategyRecord:
    """Stratégie du catalogue telle que chargée pour l'indexation."""

    id: UUID
    algo: str
    params: dict[str, Any]
    parser_slug: str | None


async def load_routing(config_pool: asyncpg.Pool, workspace_id: UUID) -> RoutingConfig:
    """Charge la config de routage fusionnée (global + workspace).

    Les lignes `workspace_id IS NULL` sont les défauts globaux ; celles du
    workspace les surchargent clé par clé (extension / catégorie).
    """
    async with config_pool.acquire() as conn:
        ext_rows = await conn.fetch(
            "SELECT workspace_id, extension, category FROM chunking_extension_categories "
            "WHERE workspace_id IS NULL OR workspace_id = $1",
            workspace_id,
        )
        cat_rows = await conn.fetch(
            "SELECT workspace_id, category, strategy_name FROM chunking_category_strategies "
            "WHERE workspace_id IS NULL OR workspace_id = $1",
            workspace_id,
        )

    ext_global = {r["extension"]: r["category"] for r in ext_rows if r["workspace_id"] is None}
    ext_ws = {r["extension"]: r["category"] for r in ext_rows if r["workspace_id"] is not None}
    cat_global = {r["category"]: r["strategy_name"] for r in cat_rows if r["workspace_id"] is None}
    cat_ws = {r["category"]: r["strategy_name"] for r in cat_rows if r["workspace_id"] is not None}

    return RoutingConfig(
        extension_categories=merge_maps(ext_global, ext_ws),
        category_strategies=merge_maps(cat_global, cat_ws),
    )


def _record_from_row(row: asyncpg.Record) -> StrategyRecord:
    params = row["params"]
    if isinstance(params, str):
        params = json.loads(params)
    return StrategyRecord(
        id=row["id"], algo=row["algo"], params=params, parser_slug=row["parser_slug"]
    )


async def load_strategy(
    config_pool: asyncpg.Pool,
    workspace_id: UUID,
    slug: str,
) -> StrategyRecord:
    """Charge une stratégie par slug : override workspace prioritaire sur système.

    Mode job (spec chunking §5) : ne résout QUE les stratégies système et les
    overrides du workspace — jamais une bibliothèque utilisateur (`owner_id`
    reste hors périmètre ici ; la résolution user-aware du mode service arrive
    avec F4). Lève `ValueError` si introuvable.
    """
    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_STRATEGY_COLUMNS} FROM chunking_strategies "  # noqa: S608
            "WHERE slug = $1 AND owner_id IS NULL "
            "AND (workspace_id IS NULL OR workspace_id = $2) "
            "ORDER BY workspace_id NULLS LAST LIMIT 1",
            slug,
            workspace_id,
        )
    if row is None:
        raise ValueError(f"chunking strategy not found: {slug!r}")
    return _record_from_row(row)


async def load_strategy_by_id(config_pool: asyncpg.Pool, strategy_id: UUID) -> StrategyRecord:
    """Charge une stratégie par id (binding des routes de régions, spec §4).

    Le binding par id est la règle d'or : aucune restriction de portée ici —
    une route ne peut référencer que des cibles validées à sa création.
    """
    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_STRATEGY_COLUMNS} FROM chunking_strategies WHERE id = $1",  # noqa: S608
            strategy_id,
        )
    if row is None:
        raise ValueError(f"chunking strategy not found: {strategy_id}")
    return _record_from_row(row)


async def load_region_routes(config_pool: asyncpg.Pool, strategy_id: UUID) -> list[RegionRoute]:
    """Charge les routes de régions d'une stratégie (spec chunking §3).

    L'ordre est stable (type puis qualifier) mais sans effet sur la
    résolution : la spécificité est gérée par `resolve_region_route`.
    """
    async with config_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT region_type, qualifier, target_strategy_id, atomic, overflow_policy "
            "FROM chunking_strategy_region_routes WHERE strategy_id = $1 "
            "ORDER BY region_type, qualifier",
            strategy_id,
        )
    return [
        RegionRoute(
            region_type=r["region_type"],
            qualifier=r["qualifier"],
            target_strategy_id=r["target_strategy_id"],
            atomic=r["atomic"],
            overflow_policy=r["overflow_policy"],
        )
        for r in rows
    ]


async def build_strategy_chunker(
    config_pool: asyncpg.Pool,
    record: StrategyRecord,
    *,
    estimator: TokenEstimator,
    provider_max_input_tokens: int,
    language: str | None = None,
) -> StructuredChunkerProtocol:
    """Construit le chunker d'une stratégie, passe régions comprise (spec §3).

    Sans `parser_slug` : délègue directement à la factory — comportement
    bit-à-bit identique à l'existant. Avec `parser_slug` : charge les routes de
    la stratégie, construit un chunker par cible référencée (profondeur 1 : le
    `parser_slug` éventuel d'une cible est ignoré, tout comme son besoin de
    langage tree-sitter — repli prose de la factory), puis assemble le
    `RoutingChunker` composite.
    """
    if record.parser_slug is None:
        return make_structured_chunker(
            algo=record.algo,
            params=record.params,
            estimator=estimator,
            provider_max_input_tokens=provider_max_input_tokens,
            language=language,
        )

    routes = await load_region_routes(config_pool, record.id)
    targets: dict[UUID, StructuredChunkerProtocol] = {}
    for target_id in {r.target_strategy_id for r in routes if r.target_strategy_id is not None}:
        target = await load_strategy_by_id(config_pool, target_id)
        targets[target_id] = make_structured_chunker(
            algo=target.algo,
            params=target.params,
            estimator=estimator,
            provider_max_input_tokens=provider_max_input_tokens,
        )
    return make_structured_chunker(
        algo=record.algo,
        params=record.params,
        estimator=estimator,
        provider_max_input_tokens=provider_max_input_tokens,
        language=language,
        parser_slug=record.parser_slug,
        region_routes=routes,
        route_targets=targets,
    )
