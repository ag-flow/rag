from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class ChunkingConfigNotFound(LookupError):  # noqa: N818 — nom métier (cf. WorkspaceNotFound, SourceNotFound)
    """Le workspace n'a pas de chunking_config (état incohérent — devrait toujours exister)."""

    def __init__(self, workspace_id: UUID | str) -> None:
        super().__init__(f"chunking_config not found for workspace {workspace_id}")
        self.workspace_id = workspace_id


def _normalize_extras(row: dict[str, Any]) -> dict[str, Any]:
    """asyncpg renvoie jsonb en str par défaut — parse si nécessaire."""
    if isinstance(row.get("extras"), str):
        row["extras"] = json.loads(row["extras"])
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
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID | str,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> dict[str, Any]:
    """INSERT ... ON CONFLICT DO UPDATE. Set updated_at=now(). Retourne la row."""
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
        strategy,
        max_chars,
        min_chars,
        overlap_chars,
        json.dumps(extras),
    )
    if row is None:
        raise RuntimeError("upsert_chunking_config: INSERT did not RETURN")
    log.info(
        "chunking_config.upserted",
        workspace_id=str(workspace_id),
        strategy=strategy,
    )
    return _normalize_extras(dict(row))
