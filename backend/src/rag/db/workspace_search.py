from __future__ import annotations

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from rag.schemas.mcp import SearchHit

log = structlog.get_logger(__name__)


async def vector_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
) -> list[SearchHit]:
    """Top-k chunks pgvector avec score cosine >= min_score.

    Stratégie : over-fetch `top_k * 4` triés par distance ivfflat (utilise
    l'index), filtre `score >= min_score` en Python, slice `top_k`.
    Pourquoi over-fetch : un `WHERE distance < threshold` AVANT le LIMIT
    désactive l'index ivfflat. On filtre après la lecture.
    """
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        # ivfflat.probes contrôle combien de listes sont sondées : 1 (défaut)
        # suffit en production (grande base) mais manque des voisins sur des
        # petits datasets (tests, espaces peu peuplés). On monte à 10 pour
        # un bon rappel tout en restant performant.
        await conn.execute("SET ivfflat.probes = 10")
        rows = await conn.fetch(
            """
            SELECT path, chunk_index, content,
                   1 - (embedding <=> $1::vector) AS score
            FROM embeddings
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            query_vec,
            top_k * 4,
        )

    hits = [
        SearchHit(
            workspace=workspace_name,
            indexer=indexer_used,
            path=r["path"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            score=float(r["score"]),
        )
        for r in rows
        if float(r["score"]) >= min_score
    ]
    return hits[:top_k]
