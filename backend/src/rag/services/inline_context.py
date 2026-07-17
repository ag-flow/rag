from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.indexer.chunking.breadcrumb import prepend_breadcrumb
from rag.indexer.chunking.hashing import compute_chunk_hash
from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, DroppedRegion
from rag.secrets.refs import is_vault_ref
from rag.services.llm_clients import call_llm_with_cached_prefix

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
    config_pool: asyncpg.Pool, *, workspace_id: UUID, path: str
) -> list[InlineBinding]:
    """Bindings `embedding_inline` actifs pour l'extension de `path`.

    Même chaîne d'activation que l'enrichissement post-index : trigger de
    l'extension → trigger prompts → LLM config — jamais actif par défaut.
    """
    extension = PurePosixPath(path).suffix.lower()
    if not extension:
        return []
    rows = await config_pool.fetch(
        """
        SELECT tp.template_id, pt.metadata_key, pt.prompt, pt.prompt_version, pt.target,
               lc.provider AS llm_provider, lc.model AS llm_model,
               lc.api_key_ref, lc.base_url AS llm_base_url
        FROM workspace_extension_trigger_prompts tp
        JOIN workspace_extension_triggers t ON t.id = tp.trigger_id
        JOIN prompt_templates pt ON pt.id = tp.template_id
        JOIN workspace_llm_configs lc ON lc.id = tp.llm_id
        WHERE t.workspace_id = $1 AND t.extension = $2
          AND t.enabled AND tp.enabled AND lc.enabled
          AND pt.timing = 'embedding_inline'
        ORDER BY tp.order_index
        """,
        workspace_id,
        extension,
    )
    return [
        InlineBinding(
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
) -> ChunkedDocument:
    """Applique les enrichissements `embedding_inline` au document découpé.

    - `target=chunk` : contexte LLM préfixé au texte embeddé de chaque chunk ;
    - `target=region:<type>[:<qualifier>]` : description LLM embeddée à la
      place des régions `parent_only` correspondantes (chunk synthétique).

    Idempotence (spec « Prompt B ») : chaque contexte est mis en cache sous
    (workspace, hash du texte SOURCE, template, prompt_version) — un chunk
    source inchangé réutilise son contexte, le diff ensembliste reste vide.
    Sans binding : retourne `doc` tel quel, zéro appel LLM.
    """
    bindings = await load_inline_bindings(config_pool, workspace_id=workspace_id, path=path)
    if not bindings:
        return doc

    children = list(doc.children)
    for binding in bindings:
        api_key = await _resolve_key(binding, resolver)
        if binding.target == "chunk":
            children = [
                await _contextualize_chunk(
                    config_pool, workspace_id, content, child, binding, api_key
                )
                for child in children
            ]
        else:
            children.extend(
                await _describe_regions(
                    config_pool, workspace_id, content, doc.dropped_regions, binding, api_key
                )
            )
    log.info(
        "inline_context.applied",
        workspace_id=str(workspace_id),
        path=path,
        bindings=len(bindings),
        chunks=len(children),
    )
    return replace(doc, children=children)


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


async def _describe_regions(
    config_pool: asyncpg.Pool,
    workspace_id: UUID,
    document: str,
    dropped: list[DroppedRegion],
    binding: InlineBinding,
    api_key: str | None,
) -> list[ChildChunk]:
    wanted_type, wanted_qualifier = _parse_region_target(binding.target)
    out: list[ChildChunk] = []
    for region in dropped:
        if region.region_type != wanted_type:
            continue
        if wanted_qualifier is not None and region.qualifier != wanted_qualifier:
            continue
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
            continue
        out.append(
            ChildChunk(
                embed_text=prepend_breadcrumb(
                    description, list(region.crumb), depth=region.breadcrumb_depth
                ),
                parent_key=region.parent_key,
                metadata={
                    "region_type": region.region_type,
                    "region_qualifier": region.qualifier,
                    "inline_context": binding.metadata_key,
                },
            )
        )
    return out


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
