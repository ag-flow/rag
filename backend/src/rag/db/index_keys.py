from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

log = structlog.get_logger(__name__)


async def list_paths_aggregate(
    workspace_pool: asyncpg.Pool,
    paths: list[str],
) -> dict[str, dict[str, Any]]:
    """Agrégats chunk_count / version_count / last_indexed_at par path."""
    if not paths:
        return {}
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            """
            SELECT path,
                   COUNT(*)::int                    AS chunk_count,
                   COUNT(DISTINCT indexed_at)::int  AS version_count,
                   MAX(indexed_at)                  AS last_indexed_at
            FROM embeddings
            WHERE path = ANY($1::text[])
            GROUP BY path
            """,
            paths,
        )
    return {
        r["path"]: {
            "chunk_count": r["chunk_count"],
            "version_count": r["version_count"],
            "last_indexed_at": r["last_indexed_at"],
        }
        for r in rows
    }


async def get_path_chunks(
    workspace_pool: asyncpg.Pool,
    path: str,
) -> list[dict[str, Any]]:
    """Chunks d'un path triés par indexed_at DESC puis chunk_index ASC."""
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            """
            SELECT chunk_index, content, metadata, indexed_at
            FROM embeddings
            WHERE path = $1
            ORDER BY indexed_at DESC, chunk_index ASC
            """,
            path,
        )
    result = []
    for r in rows:
        metadata = r["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        result.append({
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "metadata": metadata,
            "indexed_at": r["indexed_at"],
        })
    return result
