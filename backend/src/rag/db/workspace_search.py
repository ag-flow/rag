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
    """Top-k résultats pgvector avec score cosine >= min_score.

    Small-to-big auto-adaptatif (ADR 0001 §3 axe 2) : on cherche sur les
    enfants (embeddings) mais on renvoie le PARENT (`sections.content`) quand le
    chunk a une `section_id`, dédupliqué par section (meilleur score conservé).
    Les lignes legacy (`section_id` NULL) renvoient leur propre contenu et ne
    sont pas dédupliquées → comportement historique strictement préservé.

    Stratégie : over-fetch `top_k * 4` triés par distance ivfflat (utilise
    l'index), filtre `score >= min_score` + dédup en Python, slice `top_k`.
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
            SELECT e.path AS path,
                   e.chunk_index AS chunk_index,
                   COALESCE(s.content, e.content) AS content,
                   e.section_id AS section_id,
                   1 - (e.embedding <=> $1::vector) AS score
            FROM embeddings e
            LEFT JOIN sections s ON s.id = e.section_id
            ORDER BY e.embedding <=> $1::vector
            LIMIT $2
            """,
            query_vec,
            top_k * 4,
        )

    hits: list[SearchHit] = []
    seen_sections: set[int] = set()
    for r in rows:
        score = float(r["score"])
        if score < min_score:
            continue
        section_id = r["section_id"]
        if section_id is not None:
            if section_id in seen_sections:
                continue
            seen_sections.add(section_id)
        hits.append(
            SearchHit(
                workspace=workspace_name,
                indexer=indexer_used,
                path=r["path"],
                chunk_index=r["chunk_index"],
                content=r["content"],
                score=score,
            )
        )
        if len(hits) >= top_k:
            break
    return hits
