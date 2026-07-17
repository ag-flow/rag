from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from rag.indexer.chunking.hashing import compute_chunk_hash
from rag.indexer.chunking.region_registry import get_region_parser
from rag.indexer.chunking.region_routes import resolve_region_route
from rag.indexer.chunking.tokens import HeuristicTokenEstimator
from rag.schemas.chunking_preview import (
    ChunkSetDiff,
    CompareResult,
    PreviewChunk,
    PreviewParent,
    PreviewRegion,
    PreviewResult,
    PreviewStrategyRef,
)
from rag.services.chunking_routing import (
    StrategyRecord,
    build_strategy_chunker,
    load_region_routes,
)

# Bornes neutres de preview : pas de contexte provider (aucun embedding émis),
# mêmes défauts que l'outil d'inspection `diff_report.py`.
_CHAR_RATIO = 4.0
_MAX_INPUT_TOKENS = 8192


class PreviewStrategyNotFoundError(Exception):
    """Stratégie inexistante ou invisible pour cet utilisateur."""


async def preview_strategy(
    config_pool: asyncpg.Pool,
    *,
    owner_id: str,
    strategy_id: UUID,
    content: str,
) -> PreviewResult:
    """Dry-run PUR du découpage (spec chunking §6 item 7, S5.2).

    Aucun embedding, aucune écriture pgvector, aucun job : construction du
    chunker de la stratégie (routes et cibles comprises) puis chunk() en
    mémoire. La visibilité suit la bibliothèque du caller (système + mienne).
    """
    ref, record = await _load_visible_strategy(
        config_pool, owner_id=owner_id, strategy_id=strategy_id
    )
    estimator = HeuristicTokenEstimator(char_ratio=_CHAR_RATIO)
    chunker = await build_strategy_chunker(
        config_pool,
        record,
        estimator=estimator,
        provider_max_input_tokens=_MAX_INPUT_TOKENS,
    )
    doc = chunker.chunk(content)

    chunks = [
        PreviewChunk(
            index=i,
            embed_text=child.embed_text,
            tokens=estimator.estimate(child.embed_text),
            chunk_hash=compute_chunk_hash(child.embed_text),
            parent_key=child.parent_key,
            region_type=child.metadata.get("region_type"),
            region_qualifier=child.metadata.get("region_qualifier"),
        )
        for i, child in enumerate(doc.children)
    ]
    return PreviewResult(
        strategy=ref,
        parents=[
            PreviewParent(section_key=p.section_key, chars=len(p.content)) for p in doc.parents
        ],
        chunks=chunks,
        regions=await _regions_overview(config_pool, record, content),
        total_chunks=len(chunks),
        total_tokens=sum(c.tokens for c in chunks),
    )


async def compare_strategies(
    config_pool: asyncpg.Pool,
    *,
    owner_id: str,
    content: str,
    strategy_a: UUID,
    strategy_b: UUID,
) -> CompareResult:
    """Deux stratégies côte à côte + diff ensembliste par chunk_hash (S5.2)."""
    a = await preview_strategy(
        config_pool, owner_id=owner_id, strategy_id=strategy_a, content=content
    )
    b = await preview_strategy(
        config_pool, owner_id=owner_id, strategy_id=strategy_b, content=content
    )
    hashes_a = {c.chunk_hash for c in a.chunks}
    hashes_b = {c.chunk_hash for c in b.chunks}
    return CompareResult(
        a=a,
        b=b,
        diff=ChunkSetDiff(
            common=len(hashes_a & hashes_b),
            only_a=sorted(hashes_a - hashes_b),
            only_b=sorted(hashes_b - hashes_a),
        ),
    )


async def _load_visible_strategy(
    config_pool: asyncpg.Pool, *, owner_id: str, strategy_id: UUID
) -> tuple[PreviewStrategyRef, StrategyRecord]:
    row = await config_pool.fetchrow(
        "SELECT id, label, slug, algo, params, parser_slug FROM chunking_strategies s "
        "WHERE s.workspace_id IS NULL AND (s.owner_id IS NULL OR s.owner_id = $1) "
        "AND s.id = $2",
        owner_id,
        strategy_id,
    )
    if row is None:
        raise PreviewStrategyNotFoundError(str(strategy_id))
    params = row["params"]
    if isinstance(params, str):
        params = json.loads(params)
    ref = PreviewStrategyRef(
        id=row["id"],
        label=row["label"],
        slug=row["slug"],
        algo=row["algo"],
        parser_slug=row["parser_slug"],
    )
    record = StrategyRecord(
        id=row["id"], algo=row["algo"], params=params, parser_slug=row["parser_slug"]
    )
    return ref, record


async def _regions_overview(
    config_pool: asyncpg.Pool, record: StrategyRecord, content: str
) -> list[PreviewRegion]:
    """Régions du document + route résolue — montre l'atomicité appliquée et
    la politique déclenchée sans altérer le chunker (lecture parallèle)."""
    if record.parser_slug is None:
        return []
    parser = get_region_parser(record.parser_slug)
    routes = await load_region_routes(config_pool, record.id)
    out: list[PreviewRegion] = []
    for region in parser.parse(content):
        route = resolve_region_route(routes, region_type=region.type, qualifier=region.qualifier)
        out.append(
            PreviewRegion(
                region_type=region.type,
                qualifier=region.qualifier,
                start_line=region.start_line,
                end_line=region.end_line,
                routed=route is not None,
                atomic=route.atomic if route is not None else False,
                overflow_policy=route.overflow_policy if route is not None else None,
                target_strategy_id=route.target_strategy_id if route is not None else None,
            )
        )
    return out
