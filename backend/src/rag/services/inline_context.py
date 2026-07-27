from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.indexer.chunking.breadcrumb import prepend_breadcrumb
from rag.indexer.chunking.hashing import compute_chunk_hash
from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, RoutedRegion
from rag.secrets.refs import is_vault_ref
from rag.services.endpoint_throttle import estimate_tokens, llm_slot
from rag.services.llm_clients import call_llm_with_cached_prefix
from rag.services.trigger_match import resolve_trigger

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


@dataclass(frozen=True)
class InlineBinding:
    """Template d'enrichissement actif en `embedding_inline` pour un fichier."""

    template_id: UUID
    metadata_key: str
    prompt: str
    prompt_version: int
    target: str  # 'chunk' | 'region:<type>[:<qualifier>]'
    llm_provider: str
    llm_model: str
    api_key_ref: str | None
    llm_base_url: str | None


async def load_inline_bindings(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
    strategy_id: UUID | None = None,
) -> list[InlineBinding]:
    """Bindings `embedding_inline` actifs pour ce fichier — jamais par défaut.

    Deux chemins d'activation, fusionnés :
    1. triggers par pattern glob de chemin (workspace-scopés, LLM explicite
       au binding) — un seul trigger s'applique, le plus spécifique
       (`rag.services.trigger_match`) ;
    2. prompts de la STRATÉGIE résolue (S6.4) — le template voyage avec la
       stratégie ; le LLM d'exécution est la première config LLM active du
       workspace (aucune → bindings stratégie ignorés avec warning, politique
       S6.2). Un template lié par les deux chemins ne s'applique qu'une fois
       (le trigger, décision locale au workspace, gagne).
    """
    trigger = await resolve_trigger(config_pool, workspace_id=workspace_id, path=path)
    rows: list[asyncpg.Record] = []
    if trigger is not None:
        rows = await config_pool.fetch(
            """
            SELECT tp.template_id, pt.metadata_key, pt.prompt, pt.prompt_version, pt.target,
                   lc.provider AS llm_provider, lc.model AS llm_model,
                   lc.api_key_ref, lc.base_url AS llm_base_url
            FROM workspace_extension_trigger_prompts tp
            JOIN prompt_templates pt ON pt.id = tp.template_id
            JOIN workspace_llm_configs lc ON lc.id = tp.llm_id
            WHERE tp.trigger_id = $1
              AND tp.enabled AND lc.enabled
              AND pt.timing = 'embedding_inline'
            ORDER BY tp.order_index
            """,
            trigger["id"],
        )
    bindings = [_binding_from_row(r) for r in rows]
    if strategy_id is not None:
        bound = {b.template_id for b in bindings}
        bindings.extend(
            b
            for b in await _load_strategy_bindings(config_pool, workspace_id, strategy_id)
            if b.template_id not in bound
        )
    return bindings


def _binding_from_row(r: asyncpg.Record) -> InlineBinding:
    return InlineBinding(
        template_id=r["template_id"],
        metadata_key=r["metadata_key"],
        prompt=r["prompt"],
        prompt_version=r["prompt_version"],
        target=r["target"],
        llm_provider=r["llm_provider"],
        llm_model=r["llm_model"],
        api_key_ref=r["api_key_ref"],
        llm_base_url=r["llm_base_url"],
    )


async def _load_strategy_bindings(
    config_pool: asyncpg.Pool, workspace_id: UUID, strategy_id: UUID
) -> list[InlineBinding]:
    rows = await config_pool.fetch(
        """
        SELECT sp.template_id, pt.metadata_key, pt.prompt, pt.prompt_version, pt.target
        FROM chunking_strategy_prompts sp
        JOIN prompt_templates pt ON pt.id = sp.template_id
        WHERE sp.strategy_id = $1 AND sp.enabled AND pt.timing = 'embedding_inline'
        ORDER BY sp.order_index
        """,
        strategy_id,
    )
    if not rows:
        return []
    llm = await config_pool.fetchrow(
        "SELECT provider, model, api_key_ref, base_url FROM workspace_llm_configs "
        "WHERE workspace_id = $1 AND enabled ORDER BY created_at LIMIT 1",
        workspace_id,
    )
    if llm is None:
        log.warning(
            "inline_context.no_llm_for_strategy_prompts",
            workspace_id=str(workspace_id),
            strategy_id=str(strategy_id),
        )
        return []
    return [
        InlineBinding(
            template_id=r["template_id"],
            metadata_key=r["metadata_key"],
            prompt=r["prompt"],
            prompt_version=r["prompt_version"],
            target=r["target"],
            llm_provider=llm["provider"],
            llm_model=llm["model"],
            api_key_ref=llm["api_key_ref"],
            llm_base_url=llm["base_url"],
        )
        for r in rows
    ]


async def apply_inline_context(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    path: str,
    content: str,
    doc: ChunkedDocument,
    resolver: _ResolverProtocol,
    bindings: list[InlineBinding] | None = None,
) -> ChunkedDocument:
    """Applique les enrichissements `embedding_inline` au document découpé.

    - `target=chunk` : contexte LLM préfixé au texte embeddé de chaque chunk ;
    - `target=region:<type>[:<qualifier>]` : description LLM de chaque région
      ROUTÉE correspondante, embeddée en chunk synthétique — elle REMPLACE le
      source pour `parent_only`, s'AJOUTE au source sinon (S6.3). Résolution
      de spécificité alignée sur les routes : qualifier exact > type seul.

    Idempotence (spec « Prompt B ») : chaque contexte est mis en cache sous
    (workspace, hash du texte SOURCE, template, prompt_version) — un chunk
    source inchangé réutilise son contexte, le diff ensembliste reste vide.
    Échec LLM sur un chunk/une région → élément indexé SANS contexte +
    warning, jamais d'échec du job complet (S6.2). Sans binding : retourne
    `doc` tel quel, zéro appel LLM. `bindings` préchargés acceptés (le caller
    les a déjà lus pour réserver le budget tokens du normaliseur).
    """
    if bindings is None:
        bindings = await load_inline_bindings(config_pool, workspace_id=workspace_id, path=path)
    if not bindings:
        return doc

    children = list(doc.children)
    for binding in (b for b in bindings if b.target == "chunk"):
        api_key = await _resolve_key(binding, resolver)
        children = [
            await _contextualize_chunk(config_pool, workspace_id, content, child, binding, api_key)
            for child in children
        ]

    region_bindings = [b for b in bindings if b.target != "chunk"]
    for region in doc.routed_regions:
        binding = _resolve_region_binding(region, region_bindings)
        if binding is None:
            continue
        api_key = await _resolve_key(binding, resolver)
        described = await _describe_region(
            config_pool, workspace_id, content, region, binding, api_key
        )
        if described is not None:
            children.append(described)

    log.info(
        "inline_context.applied",
        workspace_id=str(workspace_id),
        path=path,
        bindings=len(bindings),
        chunks=len(children),
    )
    return replace(doc, children=children)


def _resolve_region_binding(
    region: RoutedRegion, bindings: list[InlineBinding]
) -> InlineBinding | None:
    """Spécificité décroissante (S6.3) : `region:type:qualifier` exact >
    `region:type` > rien. À spécificité égale, le premier binding (ordre
    `order_index` de la requête) gagne — un seul contexte par région."""
    generic: InlineBinding | None = None
    for binding in bindings:
        wanted_type, wanted_qualifier = _parse_region_target(binding.target)
        if wanted_type != region.region_type:
            continue
        if wanted_qualifier is not None:
            if region.qualifier == wanted_qualifier:
                return binding
        elif generic is None:
            generic = binding
    return generic


async def _resolve_key(binding: InlineBinding, resolver: _ResolverProtocol) -> str | None:
    if binding.api_key_ref and is_vault_ref(binding.api_key_ref):
        return await resolver.resolve_with_retry(binding.api_key_ref)
    return None


async def _contextualize_chunk(
    config_pool: asyncpg.Pool,
    workspace_id: UUID,
    document: str,
    child: ChildChunk,
    binding: InlineBinding,
    api_key: str | None,
) -> ChildChunk:
    source_hash = compute_chunk_hash(child.embed_text)
    context = await _get_or_generate(
        config_pool,
        workspace_id=workspace_id,
        source_hash=source_hash,
        source_text=child.embed_text,
        document=document,
        binding=binding,
        api_key=api_key,
    )
    if not context:
        return child
    return ChildChunk(
        embed_text=f"{context}\n\n{child.embed_text}",
        parent_key=child.parent_key,
        metadata={**dict(child.metadata), "inline_context": binding.metadata_key},
    )


async def _describe_region(
    config_pool: asyncpg.Pool,
    workspace_id: UUID,
    document: str,
    region: RoutedRegion,
    binding: InlineBinding,
    api_key: str | None,
) -> ChildChunk | None:
    source_hash = compute_chunk_hash(region.content)
    description = await _get_or_generate(
        config_pool,
        workspace_id=workspace_id,
        source_hash=source_hash,
        source_text=region.content,
        document=document,
        binding=binding,
        api_key=api_key,
    )
    if not description:
        return None
    return ChildChunk(
        embed_text=prepend_breadcrumb(
            description, list(region.crumb), depth=region.breadcrumb_depth
        ),
        parent_key=region.parent_key,
        metadata={
            "region_type": region.region_type,
            "region_qualifier": region.qualifier,
            "inline_context": binding.metadata_key,
            "region_source_embedded": region.source_embedded,
        },
    )


def _parse_region_target(target: str) -> tuple[str, str | None]:
    parts = target.split(":", 2)  # 'region:<type>[:<qualifier>]'
    return parts[1], (parts[2] if len(parts) > 2 else None)


async def _get_or_generate(
    config_pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    source_hash: str,
    source_text: str,
    document: str,
    binding: InlineBinding,
    api_key: str | None,
) -> str:
    cached = await config_pool.fetchval(
        "SELECT context FROM chunk_context_cache "
        "WHERE workspace_id=$1 AND source_hash=$2 AND template_id=$3 AND prompt_version=$4",
        workspace_id,
        source_hash,
        binding.template_id,
        binding.prompt_version,
    )
    if cached is not None:
        return str(cached)

    prompt = binding.prompt.replace("{chunk}", source_text).replace("{document}", "")
    try:
        # Throttling LLM cross-workspace par endpoint (enabler fe6b8dcb).
        slot = await llm_slot(config_pool, workspace_id, tokens=estimate_tokens(document, prompt))
        async with slot:
            context = (
                await call_llm_with_cached_prefix(
                    provider=binding.llm_provider,
                    model=binding.llm_model,
                    api_key=api_key,
                    base_url=binding.llm_base_url,
                    cached_prefix=document,
                    prompt=prompt,
                )
            ).strip()
    except Exception as exc:  # politique S6.2 : jamais d'échec du job complet
        log.warning(
            "inline_context.llm_failed",
            workspace_id=str(workspace_id),
            template_id=str(binding.template_id),
            error=type(exc).__name__,
        )
        return ""
    if not context:
        return ""
    await config_pool.execute(
        "INSERT INTO chunk_context_cache "
        "(workspace_id, source_hash, template_id, prompt_version, context, "
        " llm_provider, llm_model) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT DO NOTHING",
        workspace_id,
        source_hash,
        binding.template_id,
        binding.prompt_version,
        context,
        binding.llm_provider,
        binding.llm_model,
    )
    return context
