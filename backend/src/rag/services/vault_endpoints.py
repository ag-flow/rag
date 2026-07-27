from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog

from rag.schemas.vault_endpoints import (
    EndpointCreate,
    EndpointIndexerSpec,
    EndpointLlmSpec,
    EndpointOut,
    EndpointRerankSpec,
    EndpointUpdate,
    slugify,
)
from rag.services.endpoint_fallback import validate_fallback

log = structlog.get_logger(__name__)


class EndpointSlugTakenError(ValueError):
    """Un endpoint avec ce slug existe déjà dans ce coffre."""


_SELECT_BY_VAULT = """
    SELECT id, vault_id, label, slug,
           indexer_provider, indexer_model, indexer_api_key_ref, indexer_base_url,
           rerank_provider, rerank_model, rerank_api_key_ref, rerank_base_url,
           rerank_top_k,
           llm_provider, llm_model, llm_api_key_ref, llm_base_url,
           indexer_rpm_limit, indexer_tpm_limit,
           rerank_rpm_limit, rerank_tpm_limit,
           llm_rpm_limit, llm_tpm_limit,
           fallback_endpoint_id, failure_threshold, cooldown_seconds,
           indexer_max_concurrency, rerank_max_concurrency, llm_max_concurrency,
           created_at, updated_at
    FROM vault_endpoints WHERE vault_id = $1 ORDER BY label
"""

_SELECT_BY_ID = """
    SELECT id, vault_id, label, slug,
           indexer_provider, indexer_model, indexer_api_key_ref, indexer_base_url,
           rerank_provider, rerank_model, rerank_api_key_ref, rerank_base_url,
           rerank_top_k,
           llm_provider, llm_model, llm_api_key_ref, llm_base_url,
           indexer_rpm_limit, indexer_tpm_limit,
           rerank_rpm_limit, rerank_tpm_limit,
           llm_rpm_limit, llm_tpm_limit,
           fallback_endpoint_id, failure_threshold, cooldown_seconds,
           indexer_max_concurrency, rerank_max_concurrency, llm_max_concurrency,
           created_at, updated_at
    FROM vault_endpoints WHERE id = $1
"""

_INSERT = """
    INSERT INTO vault_endpoints
        (vault_id, label, slug,
         indexer_provider, indexer_model, indexer_api_key_ref, indexer_base_url,
         rerank_provider, rerank_model, rerank_api_key_ref, rerank_base_url,
         rerank_top_k,
         llm_provider, llm_model, llm_api_key_ref, llm_base_url,
         indexer_rpm_limit, indexer_tpm_limit,
         rerank_rpm_limit, rerank_tpm_limit,
         llm_rpm_limit, llm_tpm_limit,
         indexer_max_concurrency, rerank_max_concurrency, llm_max_concurrency)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
            $17, $18, $19, $20, $21, $22, $23, $24, $25)
    RETURNING id, vault_id, label, slug,
              indexer_provider, indexer_model, indexer_api_key_ref, indexer_base_url,
              rerank_provider, rerank_model, rerank_api_key_ref, rerank_base_url,
              rerank_top_k,
              llm_provider, llm_model, llm_api_key_ref, llm_base_url,
              indexer_rpm_limit, indexer_tpm_limit,
              rerank_rpm_limit, rerank_tpm_limit,
              llm_rpm_limit, llm_tpm_limit,
              fallback_endpoint_id, failure_threshold, cooldown_seconds,
              indexer_max_concurrency, rerank_max_concurrency, llm_max_concurrency,
              created_at, updated_at
"""

_UPDATE = """
    UPDATE vault_endpoints SET
        label = $2,
        indexer_provider = $3, indexer_model = $4,
        indexer_api_key_ref = $5, indexer_base_url = $6,
        rerank_provider = $7, rerank_model = $8,
        rerank_api_key_ref = $9, rerank_base_url = $10, rerank_top_k = $11,
        llm_provider = $12, llm_model = $13,
        llm_api_key_ref = $14, llm_base_url = $15,
        indexer_rpm_limit = $16, indexer_tpm_limit = $17,
        rerank_rpm_limit = $18, rerank_tpm_limit = $19,
        llm_rpm_limit = $20, llm_tpm_limit = $21,
        fallback_endpoint_id = $22, failure_threshold = $23, cooldown_seconds = $24,
        indexer_max_concurrency = $25, rerank_max_concurrency = $26,
        llm_max_concurrency = $27,
        updated_at = now()
    WHERE id = $1
    RETURNING id, vault_id, label, slug,
              indexer_provider, indexer_model, indexer_api_key_ref, indexer_base_url,
              rerank_provider, rerank_model, rerank_api_key_ref, rerank_base_url,
              rerank_top_k,
              llm_provider, llm_model, llm_api_key_ref, llm_base_url,
              indexer_rpm_limit, indexer_tpm_limit,
              rerank_rpm_limit, rerank_tpm_limit,
              llm_rpm_limit, llm_tpm_limit,
              fallback_endpoint_id, failure_threshold, cooldown_seconds,
              indexer_max_concurrency, rerank_max_concurrency, llm_max_concurrency,
              created_at, updated_at
"""


def _to_out(row: asyncpg.Record) -> EndpointOut:
    rerank = None
    if row["rerank_provider"] is not None:
        rerank = EndpointRerankSpec(
            provider=row["rerank_provider"],
            model=row["rerank_model"],
            api_key_ref=row["rerank_api_key_ref"],
            base_url=row["rerank_base_url"],
            top_k_pre_rerank=row["rerank_top_k"] or 20,
            rpm_limit=row["rerank_rpm_limit"],
            tpm_limit=row["rerank_tpm_limit"],
            max_concurrency=row["rerank_max_concurrency"],
        )
    llm = None
    if row["llm_provider"] is not None:
        llm = EndpointLlmSpec(
            provider=row["llm_provider"],
            model=row["llm_model"],
            api_key_ref=row["llm_api_key_ref"],
            base_url=row["llm_base_url"],
            rpm_limit=row["llm_rpm_limit"],
            tpm_limit=row["llm_tpm_limit"],
            max_concurrency=row["llm_max_concurrency"],
        )
    return EndpointOut(
        id=row["id"],
        vault_id=row["vault_id"],
        label=row["label"],
        slug=row["slug"],
        indexer=EndpointIndexerSpec(
            provider=row["indexer_provider"],
            model=row["indexer_model"],
            api_key_ref=row["indexer_api_key_ref"],
            base_url=row["indexer_base_url"],
            rpm_limit=row["indexer_rpm_limit"],
            tpm_limit=row["indexer_tpm_limit"],
            max_concurrency=row["indexer_max_concurrency"],
        ),
        rerank=rerank,
        llm=llm,
        fallback_endpoint_id=row["fallback_endpoint_id"],
        failure_threshold=row["failure_threshold"],
        cooldown_seconds=row["cooldown_seconds"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_endpoints(conn: asyncpg.Connection, *, vault_id: UUID) -> list[EndpointOut]:
    rows = await conn.fetch(_SELECT_BY_VAULT, vault_id)
    return [_to_out(r) for r in rows]


async def get_endpoint(conn: asyncpg.Connection, *, endpoint_id: UUID) -> EndpointOut | None:
    row = await conn.fetchrow(_SELECT_BY_ID, endpoint_id)
    return _to_out(row) if row else None


async def create_endpoint(
    conn: asyncpg.Connection, *, vault_id: UUID, req: EndpointCreate
) -> EndpointOut:
    slug = slugify(req.label)
    if not slug:
        raise ValueError("le label ne produit pas de slug valide")
    rerank = req.rerank
    try:
        row = await conn.fetchrow(
            _INSERT,
            vault_id,
            req.label,
            slug,
            req.indexer.provider,
            req.indexer.model,
            req.indexer.api_key_ref,
            req.indexer.base_url,
            rerank.provider if rerank else None,
            rerank.model if rerank else None,
            rerank.api_key_ref if rerank else None,
            rerank.base_url if rerank else None,
            rerank.top_k_pre_rerank if rerank else None,
            req.llm.provider if req.llm else None,
            req.llm.model if req.llm else None,
            req.llm.api_key_ref if req.llm else None,
            req.llm.base_url if req.llm else None,
            req.indexer.rpm_limit,
            req.indexer.tpm_limit,
            rerank.rpm_limit if rerank else None,
            rerank.tpm_limit if rerank else None,
            req.llm.rpm_limit if req.llm else None,
            req.llm.tpm_limit if req.llm else None,
            req.indexer.max_concurrency,
            rerank.max_concurrency if rerank else None,
            req.llm.max_concurrency if req.llm else None,
        )
    except asyncpg.UniqueViolationError as exc:
        raise EndpointSlugTakenError(slug) from exc
    log.info("vault_endpoint.created", vault_id=str(vault_id), slug=slug)
    return _to_out(row)


async def update_endpoint(
    conn: asyncpg.Connection, *, endpoint_id: UUID, req: EndpointUpdate
) -> EndpointOut | None:
    """Met à jour label et/ou configs. Le slug reste figé (identité stable).

    Snapshot : la modification n'affecte que les workspaces créés ensuite.
    Le fallback est validé avant écriture (même coffre, un seul niveau,
    vectorisation compatible) — lève EndpointFallbackInvalidError sinon.
    """
    current = await get_endpoint(conn, endpoint_id=endpoint_id)
    if current is None:
        return None
    label = req.label if req.label is not None else current.label
    indexer = req.indexer if req.indexer is not None else current.indexer
    rerank = (
        None if req.clear_rerank else (req.rerank if req.rerank is not None else current.rerank)
    )
    llm = None if req.clear_llm else (req.llm if req.llm is not None else current.llm)
    fallback_id = (
        None
        if req.clear_fallback
        else (
            req.fallback_endpoint_id
            if req.fallback_endpoint_id is not None
            else current.fallback_endpoint_id
        )
    )
    threshold = (
        req.failure_threshold if req.failure_threshold is not None else current.failure_threshold
    )
    cooldown = (
        req.cooldown_seconds if req.cooldown_seconds is not None else current.cooldown_seconds
    )
    if fallback_id is not None:
        # Revalidé même quand seul l'indexeur change : la compatibilité de
        # vectorisation dépend du couple (primaire, fallback).
        await validate_fallback(
            conn,
            endpoint_id=endpoint_id,
            vault_id=current.vault_id,
            fallback_id=fallback_id,
            indexer_provider=indexer.provider,
            indexer_model=indexer.model,
        )

    row = await conn.fetchrow(
        _UPDATE,
        endpoint_id,
        label,
        indexer.provider,
        indexer.model,
        indexer.api_key_ref,
        indexer.base_url,
        rerank.provider if rerank else None,
        rerank.model if rerank else None,
        rerank.api_key_ref if rerank else None,
        rerank.base_url if rerank else None,
        rerank.top_k_pre_rerank if rerank else None,
        llm.provider if llm else None,
        llm.model if llm else None,
        llm.api_key_ref if llm else None,
        llm.base_url if llm else None,
        indexer.rpm_limit,
        indexer.tpm_limit,
        rerank.rpm_limit if rerank else None,
        rerank.tpm_limit if rerank else None,
        llm.rpm_limit if llm else None,
        llm.tpm_limit if llm else None,
        fallback_id,
        threshold,
        cooldown,
        indexer.max_concurrency,
        rerank.max_concurrency if rerank else None,
        llm.max_concurrency if llm else None,
    )
    log.info("vault_endpoint.updated", endpoint_id=str(endpoint_id))
    return _to_out(row)


async def delete_endpoint(conn: asyncpg.Connection, *, endpoint_id: UUID) -> bool:
    """Supprime l'endpoint. Les workspaces existants (snapshot) ne sont pas affectés."""
    result = await conn.execute("DELETE FROM vault_endpoints WHERE id = $1", endpoint_id)
    return result != "DELETE 0"
