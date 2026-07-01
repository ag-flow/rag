from __future__ import annotations

import json
from collections import defaultdict
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


async def get_document_sections(
    workspace_pool: asyncpg.Pool,
    path: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Sections structurées d'un path avec leurs chunks embeddés.

    Retourne (sections, is_legacy).
    is_legacy=True quand le document n'a pas de sections (pipeline legacy).
    Dans ce cas, chaque embedding est exposé comme une section autonome.
    """
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)

        section_rows = await conn.fetch(
            """
            SELECT id, section_index, section_key, content, metadata
            FROM sections
            WHERE path = $1
            ORDER BY section_index NULLS LAST, id
            """,
            path,
        )

        if section_rows:
            section_ids = [r["id"] for r in section_rows]
            chunk_rows = await conn.fetch(
                """
                SELECT section_id, chunk_index, content, metadata
                FROM embeddings
                WHERE section_id = ANY($1)
                ORDER BY section_id, chunk_index
                """,
                section_ids,
            )

            chunks_by_section: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for c in chunk_rows:
                meta = c["metadata"]
                if isinstance(meta, str):
                    meta = json.loads(meta)
                chunks_by_section[c["section_id"]].append({
                    "chunk_index": c["chunk_index"],
                    "embed_text": c["content"],
                    "metadata": meta or {},
                })

            sections = []
            for s in section_rows:
                meta = s["metadata"]
                if isinstance(meta, str):
                    meta = json.loads(meta)
                sections.append({
                    "section_index": s["section_index"] if s["section_index"] is not None else 0,
                    "section_key": s["section_key"],
                    "content": s["content"],
                    "metadata": meta or {},
                    "chunks": chunks_by_section.get(s["id"], []),
                })
            return sections, False

        # Fallback legacy : embeddings sans section_id
        legacy_rows = await conn.fetch(
            """
            SELECT chunk_index, content, metadata
            FROM embeddings
            WHERE path = $1 AND section_id IS NULL
            ORDER BY chunk_index
            """,
            path,
        )

        sections = []
        for r in legacy_rows:
            meta = r["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            sections.append({
                "section_index": r["chunk_index"],
                "section_key": f"chunk_{r['chunk_index']}",
                "content": r["content"],
                "metadata": meta or {},
                "chunks": [{
                    "chunk_index": r["chunk_index"],
                    "embed_text": r["content"],
                    "metadata": meta or {},
                }],
            })
        return sections, True
