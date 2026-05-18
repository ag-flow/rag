from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.api.errors import ChunkingConfigNotFound
from rag.schemas.admin import ChunkingConfigSpec

__all__ = [
    "ChunkingConfigNotFound",
    "get_chunking_config",
    "upsert_chunking_config",
]

log = structlog.get_logger(__name__)


def _normalize_extras(row: dict[str, Any]) -> dict[str, Any]:
    """asyncpg renvoie jsonb en str par défaut — parse si nécessaire.

    Pure : ne mute pas `row`, retourne soit `row` inchangée soit une copie
    avec `extras` parsé.
    """
    extras = row.get("extras")
    if isinstance(extras, str):
        return {**row, "extras": json.loads(extras)}
    return row


async def get_chunking_config(
    workspace_id: UUID | str,
    config_pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Retourne la chunking_config du workspace. Raise ChunkingConfigNotFound si absente."""
    row = await config_pool.fetchrow(
        """
        SELECT workspace_id, strategy, max_chars, min_chars, overlap_chars,
               extras, created_at, updated_at
        FROM chunking_configs
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    if row is None:
        raise ChunkingConfigNotFound(workspace_id)
    return _normalize_extras(dict(row))


async def upsert_chunking_config(
    *,
    workspace_id: UUID | str,
    spec: ChunkingConfigSpec,
    config_pool: asyncpg.Pool,
) -> dict[str, Any]:
    """INSERT ... ON CONFLICT DO UPDATE. Set updated_at=now(). Retourne la row.

    La validation métier (min<max, overlap<max, extras non vide interdit pour
    strategy='paragraph') est portée par `ChunkingConfigSpec`.
    """
    row = await config_pool.fetchrow(
        """
        INSERT INTO chunking_configs
            (workspace_id, strategy, max_chars, min_chars, overlap_chars, extras)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        ON CONFLICT (workspace_id) DO UPDATE
            SET strategy      = EXCLUDED.strategy,
                max_chars     = EXCLUDED.max_chars,
                min_chars     = EXCLUDED.min_chars,
                overlap_chars = EXCLUDED.overlap_chars,
                extras        = EXCLUDED.extras,
                updated_at    = now()
        RETURNING workspace_id, strategy, max_chars, min_chars, overlap_chars,
                  extras, created_at, updated_at
        """,
        workspace_id,
        spec.strategy,
        spec.max_chars,
        spec.min_chars,
        spec.overlap_chars,
        json.dumps(spec.extras),
    )
    if row is None:
        raise RuntimeError("upsert_chunking_config: INSERT did not RETURN")
    log.info(
        "chunking_config.upserted",
        workspace_id=str(workspace_id),
        strategy=spec.strategy,
    )
    return _normalize_extras(dict(row))
