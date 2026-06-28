from __future__ import annotations

import asyncio
from dataclasses import dataclass

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from rag.schemas.mcp import SearchHit

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _ChildHit:
    """Hit brut d'un bras (vectoriel ou lexical), avant dédup section."""

    path: str
    chunk_index: int
    chunk_hash: str | None
    section_id: int | None
    content: str
    score: float

    @property
    def identity(self) -> tuple:
        if self.chunk_hash is not None:
            return (self.path, self.chunk_hash)
        return (self.path, self.chunk_index)


@dataclass
class _FusedHit:
    """Résultat de la fusion RRF, avant dédup section et conversion SearchHit."""

    identity: tuple
    path: str
    chunk_index: int
    section_id: int | None
    content: str
    rrf_score: float
    vector_rank: int | None
    vector_score: float | None
    lexical_rank: int | None
    lexical_score: float | None


def rrf_fuse(
    vector_hits: list[_ChildHit],
    lexical_hits: list[_ChildHit],
    k: int = 60,
) -> list[_FusedHit]:
    """Reciprocal Rank Fusion de deux listes de hits enfants.

    Identité = (path, chunk_hash) si chunk_hash non-null, sinon (path, chunk_index) legacy.
    score_rrf = Σ 1/(k + rang) pour chaque bras où le chunk figure.
    """
    v_rank: dict[tuple, tuple[int, float]] = {
        h.identity: (i + 1, h.score) for i, h in enumerate(vector_hits)
    }
    l_rank: dict[tuple, tuple[int, float]] = {
        h.identity: (i + 1, h.score) for i, h in enumerate(lexical_hits)
    }

    seen: dict[tuple, _ChildHit] = {}
    for h in vector_hits:
        seen.setdefault(h.identity, h)
    for h in lexical_hits:
        seen.setdefault(h.identity, h)

    results: list[_FusedHit] = []
    for identity, hit in seen.items():
        vr_vs = v_rank.get(identity)
        lr_ls = l_rank.get(identity)
        rrf = 0.0
        if vr_vs is not None:
            rrf += 1.0 / (k + vr_vs[0])
        if lr_ls is not None:
            rrf += 1.0 / (k + lr_ls[0])
        results.append(
            _FusedHit(
                identity=identity,
                path=hit.path,
                chunk_index=hit.chunk_index,
                section_id=hit.section_id,
                content=hit.content,
                rrf_score=rrf,
                vector_rank=vr_vs[0] if vr_vs else None,
                vector_score=vr_vs[1] if vr_vs else None,
                lexical_rank=lr_ls[0] if lr_ls else None,
                lexical_score=lr_ls[1] if lr_ls else None,
            )
        )
    results.sort(key=lambda h: h.rrf_score, reverse=True)
    return results


async def _fetch_vector_children(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k_fetch: int,
    min_score: float,
) -> list[_ChildHit]:
    """Récupère les hits vectoriels bruts (sans dédup section)."""
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        await conn.execute("SET ivfflat.probes = 10")
        rows = await conn.fetch(
            """
            SELECT e.path AS path,
                   e.chunk_index AS chunk_index,
                   e.chunk_hash AS chunk_hash,
                   e.section_id AS section_id,
                   COALESCE(s.content, e.content) AS content,
                   1 - (e.embedding <=> $1::vector) AS score
            FROM embeddings e
            LEFT JOIN sections s ON s.id = e.section_id
            ORDER BY e.embedding <=> $1::vector
            LIMIT $2
            """,
            query_vec,
            top_k_fetch,
        )
    return [
        _ChildHit(
            path=r["path"],
            chunk_index=r["chunk_index"],
            chunk_hash=r["chunk_hash"],
            section_id=r["section_id"],
            content=r["content"],
            score=float(r["score"]),
        )
        for r in rows
        if float(r["score"]) >= min_score
    ]


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
    children = await _fetch_vector_children(
        workspace_pool,
        query_vec=query_vec,
        top_k_fetch=top_k * 4,
        min_score=min_score,
    )
    hits: list[SearchHit] = []
    seen_sections: set[int] = set()
    for child in children:
        if child.section_id is not None:
            if child.section_id in seen_sections:
                continue
            seen_sections.add(child.section_id)
        hits.append(
            SearchHit(
                workspace=workspace_name,
                indexer=indexer_used,
                path=child.path,
                chunk_index=child.chunk_index,
                content=child.content,
                score=child.score,
            )
        )
        if len(hits) >= top_k:
            break
    return hits


async def lexical_search(
    workspace_pool: asyncpg.Pool,
    *,
    query: str,
    top_k_fetch: int,
    fts_config: str = "simple",
) -> list[_ChildHit]:
    """Recherche FTS via content_tsv (websearch_to_tsquery, sans stemming).

    Pas de filtre min_score : la correspondance est déjà filtrée par `@@`.
    Pas de dédup section : fait par hybrid_search après RRF.
    """
    async with workspace_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.path AS path,
                   e.chunk_index AS chunk_index,
                   e.chunk_hash AS chunk_hash,
                   e.section_id AS section_id,
                   COALESCE(s.content, e.content) AS content,
                   ts_rank(e.content_tsv, websearch_to_tsquery($2, $1)) AS lexical_score
            FROM embeddings e
            LEFT JOIN sections s ON s.id = e.section_id
            WHERE e.content_tsv @@ websearch_to_tsquery($2, $1)
            ORDER BY lexical_score DESC
            LIMIT $3
            """,
            query,
            fts_config,
            top_k_fetch,
        )
    return [
        _ChildHit(
            path=r["path"],
            chunk_index=r["chunk_index"],
            chunk_hash=r["chunk_hash"],
            section_id=r["section_id"],
            content=r["content"],
            score=float(r["lexical_score"]),
        )
        for r in rows
    ]


async def hybrid_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    query: str,
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
    rrf_k: int = 60,
    fts_config: str = "simple",
    debug: bool = False,
) -> list[SearchHit]:
    """Recherche hybride : vectorielle + lexicale, fusionnées par RRF.

    min_score filtre le bras vectoriel uniquement.
    Dédup small-to-big (section_id) après fusion RRF.
    debug=True : chaque SearchHit porte une DebugTrace.
    """
    top_k_fetch = top_k * 4

    vector_children, lexical_children = await asyncio.gather(
        _fetch_vector_children(
            workspace_pool,
            query_vec=query_vec,
            top_k_fetch=top_k_fetch,
            min_score=min_score,
        ),
        lexical_search(
            workspace_pool,
            query=query,
            top_k_fetch=top_k_fetch,
            fts_config=fts_config,
        ),
    )

    fused = rrf_fuse(vector_children, lexical_children, k=rrf_k)

    hits: list[SearchHit] = []
    seen_sections: set[int] = set()
    for rank, fh in enumerate(fused, start=1):
        if fh.section_id is not None:
            if fh.section_id in seen_sections:
                continue
            seen_sections.add(fh.section_id)

        dbg = None
        if debug:
            from rag.schemas.mcp import DebugTrace

            dbg = DebugTrace(
                vector_rank=fh.vector_rank,
                vector_score=fh.vector_score,
                lexical_rank=fh.lexical_rank,
                lexical_score=fh.lexical_score,
                rrf_score=fh.rrf_score,
                final_rank=rank,
            )

        hits.append(
            SearchHit(
                workspace=workspace_name,
                indexer=indexer_used,
                path=fh.path,
                chunk_index=fh.chunk_index,
                content=fh.content,
                score=fh.rrf_score,
                debug=dbg,
            )
        )
        if len(hits) >= top_k:
            break

    return hits
