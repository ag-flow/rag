from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from rag.indexer.chunking.resolution import RoutingConfig, merge_maps


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


async def load_strategy(
    config_pool: asyncpg.Pool,
    workspace_id: UUID,
    name: str,
) -> tuple[str, dict[str, Any]]:
    """Charge une stratégie nommée : workspace prioritaire sur global.

    Retourne `(algo, params)`. Lève `ValueError` si introuvable.
    """
    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT algo, params FROM chunking_strategies "
            "WHERE name = $1 AND (workspace_id IS NULL OR workspace_id = $2) "
            "ORDER BY workspace_id NULLS LAST LIMIT 1",
            name,
            workspace_id,
        )
    if row is None:
        raise ValueError(f"chunking strategy not found: {name!r}")
    params = row["params"]
    if isinstance(params, str):
        params = json.loads(params)
    return row["algo"], params
