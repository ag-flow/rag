from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def get_index_status(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    """Agrégats indexed_documents + bloc sync (workspace_sources + dernier index_job)."""
    agg = await config_pool.fetchrow(
        "SELECT COUNT(*) AS documents_count, MAX(indexed_at) AS last_indexed_at "
        "FROM indexed_documents WHERE workspace_id = $1",
        workspace_id,
    )
    src = await config_pool.fetchrow(
        "SELECT last_indexed_at, next_sync_at FROM workspace_sources "
        "WHERE workspace_id = $1 LIMIT 1",
        workspace_id,
    )
    job = await config_pool.fetchrow(
        "SELECT status, finished_at FROM index_jobs "
        "WHERE workspace_id = $1 ORDER BY finished_at DESC NULLS LAST LIMIT 1",
        workspace_id,
    )
    healthy = bool(job is None or job["status"] != "error")
    return {
        "documents_count": agg["documents_count"] if agg else 0,
        "last_indexed_at": str(agg["last_indexed_at"]) if agg and agg["last_indexed_at"] else None,
        "sync": {
            "last_indexed_at": (
                str(src["last_indexed_at"]) if src and src["last_indexed_at"] else None
            ),
            "next_sync_at": str(src["next_sync_at"]) if src and src["next_sync_at"] else None,
            "last_job_status": job["status"] if job else None,
            "last_job_finished_at": str(job["finished_at"]) if job and job["finished_at"] else None,
            "healthy": healthy,
        },
    }


async def get_document_status(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
) -> dict[str, Any] | None:
    """Fraîcheur et hash d'un document indexé."""
    row = await config_pool.fetchrow(
        "SELECT path, content_hash, indexed_at, indexer_used, title "
        "FROM indexed_documents WHERE workspace_id = $1 AND path = $2",
        workspace_id,
        path,
    )
    if row is None:
        return None
    return {
        "path": row["path"],
        "content_hash": row["content_hash"],
        "indexed_at": str(row["indexed_at"]) if row["indexed_at"] else None,
        "indexer_used": row["indexer_used"],
        "title": row["title"],
    }


async def search_files_in_workspace(
    ws_pool: asyncpg.Pool,
    *,
    pattern: str,
    mode: str = "exact",
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """Recherche littérale dans le contenu indexé (embeddings).

    Modes :
    - exact      : content_tsv @@ websearch_to_tsquery (token, sans stemming)
    - substring  : ILIKE '%pattern%'
    - regex      : content ~ pattern (seq scan)

    Résultats dédupliqués par path (un path → extrait du meilleur chunk).
    """
    async with ws_pool.acquire() as conn:
        if mode == "exact":
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (path) path, content, chunk_index, metadata
                FROM embeddings
                WHERE content_tsv @@ websearch_to_tsquery('simple', $1)
                ORDER BY path, chunk_index
                LIMIT $2
                """,
                pattern,
                top_k,
            )
        elif mode == "regex":
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (path) path, content, chunk_index, metadata
                FROM embeddings
                WHERE content ~ $1
                ORDER BY path, chunk_index
                LIMIT $2
                """,
                pattern,
                top_k,
            )
        else:  # substring
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (path) path, content, chunk_index, metadata
                FROM embeddings
                WHERE content ILIKE '%' || $1 || '%'
                ORDER BY path, chunk_index
                LIMIT $2
                """,
                pattern,
                top_k,
            )
    return [
        {
            "path": r["path"],
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "enrichment_key": (
                dict(r["metadata"]).get("enrichment_key") if r["metadata"] else None
            ),
            "source_path": (
                dict(r["metadata"]).get("source_path") if r["metadata"] else None
            ),
        }
        for r in rows
    ]


async def reconstruct_document(
    ws_pool: asyncpg.Pool,
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
) -> dict[str, Any] | None:
    """Reconstruit le contenu d'un path depuis les sections (ou fallback embeddings legacy).

    Option A (M18 reco) : sections ordonnées par section_index.
    Fallback legacy : embeddings sans section_id, ordonnés par chunk_index.

    Note : la reconstruction code est approximative (tree-sitter découpe par symboles,
    pas ligne à ligne). Le contenu est celui indexé, pas le fichier source original.
    """
    async with ws_pool.acquire() as conn:
        # Tentative 1 : sections structurées
        sections = await conn.fetch(
            """
            SELECT content, section_index, section_key, metadata
            FROM sections
            WHERE path = $1
            ORDER BY section_index NULLS LAST, id
            """,
            path,
        )

        if sections:
            parts = [r["content"] for r in sections]
            is_code = any(
                r["metadata"] and dict(r["metadata"]).get("scope") for r in sections
            )
            return {
                "content": "\n\n".join(parts),
                "is_legacy": False,
                "is_code_structured": bool(is_code),
                "sections_count": len(sections),
            }

        # Fallback legacy : embeddings sans section_id
        chunks = await conn.fetch(
            """
            SELECT content, chunk_index
            FROM embeddings
            WHERE path = $1 AND section_id IS NULL
            ORDER BY chunk_index
            """,
            path,
        )

    if not chunks:
        return None

    parts = [r["content"] for r in chunks]
    return {
        "content": "\n\n".join(parts),
        "is_legacy": True,
        "is_code_structured": False,
        "sections_count": len(chunks),
    }
