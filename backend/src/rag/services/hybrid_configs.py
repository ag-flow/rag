from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def get_hybrid_config(
    workspace_id: UUID | str,
    config_pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Config de recherche hybride du workspace, ou None (vectoriel pur).

    Service public partagé par le REST admin, le REST apikey et les outils MCP —
    évite la dérive entre le SQL inline de l'endpoint admin et `_load_hybrid_config`.
    """
    row = await config_pool.fetchrow(
        """
        SELECT workspace_id, enabled, rrf_k, weight_lexical, weight_vector,
               lexical_engine, created_at, updated_at
        FROM hybrid_configs
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    return dict(row) if row is not None else None
