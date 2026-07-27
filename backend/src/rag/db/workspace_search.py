from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from rag.schemas.mcp import SearchHit

log = structlog.get_logger(__name__)


def _parse_metadata(raw: Any) -> dict[str, Any] | None:
    """Normalise la colonne jsonb `metadata` (asyncpg la renvoie en `str`).

    Aucun codec jsonb n'est enregistré au niveau du pool : il faut donc
    parser explicitement la string, comme dans `index_keys.py`.
    """
    if not raw:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


@dataclass(frozen=True)
class _ChildHit:
    """Hit brut d'un bras (vectoriel ou lexical), avant dédup section."""

    path: str
    chunk_index: int
    chunk_hash: str | None
    section_id: int | None
    content: str
    score: float
    metadata: dict[str, Any] | None = None

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
    metadata: dict[str, Any] | None = None


def rrf_fuse(
    vector_hits: list[_ChildHit],
    lexical_hits: list[_ChildHit],
    k: int = 60,
    *,
    w_vector: float = 0.5,
    w_lexical: float = 0.5,
) -> list[_FusedHit]:
    """Reciprocal Rank Fusion PONDÉRÉ de deux listes de hits enfants (D6).

    Identité = (path, chunk_hash) si chunk_hash non-null, sinon (path, chunk_index) legacy.
    score_rrf = Σ wᵢ/(k + rangᵢ) — fusion par RANGS, jamais par scores bruts
    (incomparables entre canaux). Poids par défaut 50/50.
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
            rrf += w_vector / (k + vr_vs[0])
        if lr_ls is not None:
            rrf += w_lexical / (k + lr_ls[0])
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
                metadata=hit.metadata,
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
                   1 - (e.embedding <=> $1::vector) AS score,
                   e.metadata AS metadata
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
            metadata=_parse_metadata(r["metadata"]),
        )
        for r in rows
        if float(r["score"]) >= min_score
    ]


def _enrich_hit_fields(metadata: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Retourne (enrichment_key, source_path) depuis la metadata du chunk."""
    if not metadata:
        return None, None
    return metadata.get("enrichment_key"), metadata.get("source_path")


def _apply_enrichment_filter(
    children: list[_ChildHit],
    *,
    scope: str,
    enrichment_keys: list[str] | None,
) -> list[_ChildHit]:
    """Filtre par scope (both/raw_only/enriched_only) et par enrichment_keys.

    Les raw (sans enrichment_key) passent toujours sauf si scope='enriched_only'.
    Les enrichissements passent sauf si scope='raw_only' ou filtrés par enrichment_keys.
    """
    result = []
    for h in children:
        ek = h.metadata.get("enrichment_key") if h.metadata else None
        is_enriched = bool(ek)
        if scope == "raw_only" and is_enriched:
            continue
        if scope == "enriched_only" and not is_enriched:
            continue
        if enrichment_keys and is_enriched and ek not in enrichment_keys:
            continue
        result.append(h)
    return result


def _apply_enrichment_filter_fused(
    fused: list[_FusedHit],
    *,
    scope: str,
    enrichment_keys: list[str] | None,
) -> list[_FusedHit]:
    """Même logique que _apply_enrichment_filter mais pour _FusedHit."""
    result = []
    for fh in fused:
        ek = fh.metadata.get("enrichment_key") if fh.metadata else None
        is_enriched = bool(ek)
        if scope == "raw_only" and is_enriched:
            continue
        if scope == "enriched_only" and not is_enriched:
            continue
        if enrichment_keys and is_enriched and ek not in enrichment_keys:
            continue
        result.append(fh)
    return result


async def vector_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
    scope: str = "both",
    enrichment_keys: list[str] | None = None,
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
    children = _apply_enrichment_filter(children, scope=scope, enrichment_keys=enrichment_keys)
    hits: list[SearchHit] = []
    seen_sections: set[int] = set()
    for child in children:
        if child.section_id is not None:
            if child.section_id in seen_sections:
                continue
            seen_sections.add(child.section_id)
        ek, sp = _enrich_hit_fields(child.metadata)
        hits.append(
            SearchHit(
                workspace=workspace_name,
                indexer=indexer_used,
                path=child.path,
                chunk_index=child.chunk_index,
                content=child.content,
                score=child.score,
                metadata=child.metadata,
                enrichment_key=ek,
                source_path=sp,
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
) -> list[_ChildHit]:
    """Recherche FTS bilingue sur `content_tsv` (D4, SR2.2).

    Symétrie requête/index ABSOLUE : la requête subit le même double
    traitement que la colonne générée (workspace migration 005) —
    `simple`+unaccent (match exact, poids A) || `french` (racines, poids B).
    ts_rank (poids par défaut A=1.0 > B=0.4) fait dominer le match exact.
    Pas de filtre min_score : la correspondance est déjà filtrée par `@@`.
    Pas de dédup section : fait par hybrid_search après RRF.
    """
    async with workspace_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH q AS (
                SELECT websearch_to_tsquery('simple', immutable_unaccent($1))
                       || websearch_to_tsquery('french', immutable_unaccent($1)) AS tsq
            )
            SELECT e.path AS path,
                   e.chunk_index AS chunk_index,
                   e.chunk_hash AS chunk_hash,
                   e.section_id AS section_id,
                   COALESCE(s.content, e.content) AS content,
                   ts_rank(e.content_tsv, q.tsq) AS lexical_score,
                   e.metadata AS metadata
            FROM embeddings e
            CROSS JOIN q
            LEFT JOIN sections s ON s.id = e.section_id
            WHERE e.content_tsv @@ q.tsq
            ORDER BY lexical_score DESC
            LIMIT $2
            """,
            query,
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
            metadata=_parse_metadata(r["metadata"]),
        )
        for r in rows
    ]


class _LexicalSearcher(Protocol):
    async def search(
        self, workspace_pool: asyncpg.Pool, *, query: str, top_k_fetch: int
    ) -> list[_ChildHit]: ...


@dataclass(frozen=True)
class ChannelEntry:
    """Entrée d'une liste par canal (flag debug, D8)."""

    path: str
    chunk_index: int
    rank: int
    score: float


@dataclass(frozen=True)
class HybridResult:
    """Hits fusionnés + listes brutes par canal (matière du debug D8)."""

    hits: list[SearchHit]
    vector_channel: list[ChannelEntry]
    lexical_channel: list[ChannelEntry]


def _channel(children: list[_ChildHit]) -> list[ChannelEntry]:
    return [
        ChannelEntry(path=h.path, chunk_index=h.chunk_index, rank=i + 1, score=h.score)
        for i, h in enumerate(children)
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
    lexical_engine: _LexicalSearcher,
    rrf_k: int = 60,
    w_vector: float = 0.5,
    w_lexical: float = 0.5,
    scope: str = "both",
    enrichment_keys: list[str] | None = None,
) -> HybridResult:
    """Recherche hybride : vectorielle + lexicale (moteur injecté, D5),
    fusionnées par RRF pondéré (D6). Les deux canaux s'exécutent en
    PARALLÈLE (D8).

    min_score filtre le bras vectoriel uniquement.
    Dédup small-to-big (section_id) après fusion RRF.
    Provenance TOUJOURS exposée (DebugTrace par hit, D8) ; les listes par
    canal sont retournées dans HybridResult pour le flag debug de l'API.
    """
    top_k_fetch = top_k * 4

    vector_children, lexical_children = await asyncio.gather(
        _fetch_vector_children(
            workspace_pool,
            query_vec=query_vec,
            top_k_fetch=top_k_fetch,
            min_score=min_score,
        ),
        lexical_engine.search(
            workspace_pool,
            query=query,
            top_k_fetch=top_k_fetch,
        ),
    )

    fused = rrf_fuse(
        vector_children, lexical_children, k=rrf_k, w_vector=w_vector, w_lexical=w_lexical
    )
    fused = _apply_enrichment_filter_fused(fused, scope=scope, enrichment_keys=enrichment_keys)

    hits: list[SearchHit] = []
    seen_sections: set[int] = set()
    for rank, fh in enumerate(fused, start=1):
        if fh.section_id is not None:
            if fh.section_id in seen_sections:
                continue
            seen_sections.add(fh.section_id)

        from rag.schemas.mcp import DebugTrace

        # Provenance TOUJOURS exposée (D8) — rangs par canal + score fusionné.
        dbg = DebugTrace(
            vector_rank=fh.vector_rank,
            vector_score=fh.vector_score,
            lexical_rank=fh.lexical_rank,
            lexical_score=fh.lexical_score,
            rrf_score=fh.rrf_score,
            final_rank=rank,
        )

        ek, sp = _enrich_hit_fields(fh.metadata)
        hits.append(
            SearchHit(
                workspace=workspace_name,
                indexer=indexer_used,
                path=fh.path,
                chunk_index=fh.chunk_index,
                content=fh.content,
                score=fh.rrf_score,
                metadata=fh.metadata,
                enrichment_key=ek,
                source_path=sp,
                debug=dbg,
            )
        )
        if len(hits) >= top_k:
            break

    return HybridResult(
        hits=hits,
        vector_channel=_channel(vector_children),
        lexical_channel=_channel(lexical_children),
    )
