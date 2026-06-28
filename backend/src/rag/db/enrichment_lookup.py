from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def get_enrichment(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
    key: str,
) -> dict[str, Any] | None:
    """Retourne le résultat canonique d'un enrichissement depuis document_enrichments.

    `path` est le path RÉEL du fichier source (pas le path synthétique path::key).
    Retourne None si absent. Si result_type='json', `result` est du JSON sérialisé.
    """
    row = await config_pool.fetchrow(
        """
        SELECT result, result_type, result_schema
        FROM document_enrichments
        WHERE workspace_id = $1
          AND path = $2
          AND metadata_key = $3
        """,
        workspace_id,
        path,
        key,
    )
    if row is None:
        return None
    return {
        "result": row["result"],
        "result_type": row["result_type"],
        "result_schema": row["result_schema"],
    }
