from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.admin import IndexerSpec, RerankSpec
from rag.services.jobs import reindex_workspace
from rag.services.rerank_configs import delete_rerank_config, upsert_rerank_config
from rag.services.vault_endpoints import get_endpoint

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


class NoEndpointLinkedError(Exception):
    """Workspace créé avant le lien endpoint : rien à recopier."""


class EndpointGoneError(Exception):
    """L'endpoint d'origine du workspace a été supprimé."""


class DefaultVaultMissingError(Exception):
    """Aucun coffre par défaut configuré alors qu'un secret doit être résolu."""


async def refresh_workspace_from_endpoint(
    *,
    workspace_id: UUID,
    workspace_name: str,
    confirm: bool,
    config_pool: asyncpg.Pool,
    admin_dsn: str,
    resolver: _ResolverProtocol,
    default_vault_name: str | None,
) -> dict[str, Any]:
    """Recopie la config (indexer/rerank/llm) depuis l'ENDPOINT D'ORIGINE du
    workspace — pas de changement d'endpoint possible.

    - clé/base_url seuls modifiés → UPDATE direct (vecteurs valides) ;
    - provider/modèle d'embedding modifiés → flow reindex (re-vectorisation,
      `IndexerChangeRequiresReindex` sans confirm) ;
    - rerank et llm : remplacés par la config de l'endpoint (retirés si
      l'endpoint ne les définit plus).

    Extraite du handler REST pour être partagée avec l'outil MCP
    `reset_workspace_from_endpoint` (même flow, zéro duplication).
    """
    row = await config_pool.fetchrow(
        "SELECT w.endpoint_id, ic.provider, ic.model, ic.api_key_ref, ic.base_url, "
        "ic.rpm_limit, ic.tpm_limit "
        "FROM workspaces w JOIN indexer_configs ic ON ic.workspace_id = w.id "
        "WHERE w.id = $1",
        workspace_id,
    )
    if row["endpoint_id"] is None:
        raise NoEndpointLinkedError(workspace_name)
    async with config_pool.acquire() as conn:
        endpoint = await get_endpoint(conn, endpoint_id=row["endpoint_id"])
    if endpoint is None:
        raise EndpointGoneError(workspace_name)

    def _default_vault() -> str:
        if default_vault_name is None:
            raise DefaultVaultMissingError()
        return default_vault_name

    result: dict[str, Any] = {"indexer": "unchanged", "rerank": "none", "llm": "none", "job": None}

    # ── Indexeur ────────────────────────────────────────────────────────
    ep_idx = endpoint.indexer
    model_changed = (ep_idx.provider, ep_idx.model) != (row["provider"], row["model"])
    cfg_changed = (
        ep_idx.api_key_ref or None,
        ep_idx.base_url or None,
        ep_idx.rpm_limit,
        ep_idx.tpm_limit,
    ) != (
        row["api_key_ref"] or None,
        row["base_url"] or None,
        row["rpm_limit"],
        row["tpm_limit"],
    )
    if model_changed:
        job = await reindex_workspace(
            name=workspace_name,
            new_indexer=IndexerSpec(
                provider=ep_idx.provider,
                model=ep_idx.model,
                api_key_ref=ep_idx.api_key_ref,
                base_url=ep_idx.base_url,
            ),
            confirm=confirm,
            config_pool=config_pool,
            admin_dsn=admin_dsn,
            resolver=resolver,
            default_vault_name=_default_vault(),
        )
        await config_pool.execute(
            "UPDATE indexer_configs SET rpm_limit=$2, tpm_limit=$3 WHERE workspace_id=$1",
            workspace_id,
            ep_idx.rpm_limit,
            ep_idx.tpm_limit,
        )
        result["indexer"] = "reindex_triggered"
        result["job"] = job
    elif cfg_changed:
        # Même modèle : rotation de clé / d'URL / limites — vecteurs valides.
        await config_pool.execute(
            "UPDATE indexer_configs SET api_key_ref=$2, base_url=$3, "
            "rpm_limit=$4, tpm_limit=$5 WHERE workspace_id=$1",
            workspace_id,
            ep_idx.api_key_ref,
            ep_idx.base_url,
            ep_idx.rpm_limit,
            ep_idx.tpm_limit,
        )
        result["indexer"] = "updated"

    # ── Rerank ──────────────────────────────────────────────────────────
    if endpoint.rerank is not None:
        await upsert_rerank_config(
            workspace_id=workspace_id,
            spec=RerankSpec(
                provider=endpoint.rerank.provider,  # type: ignore[arg-type]
                model=endpoint.rerank.model,
                api_key_ref=endpoint.rerank.api_key_ref,
                base_url=endpoint.rerank.base_url,
                top_k_pre_rerank=endpoint.rerank.top_k_pre_rerank,
                rpm_limit=endpoint.rerank.rpm_limit,
                tpm_limit=endpoint.rerank.tpm_limit,
            ),
            config_pool=config_pool,
            resolver=resolver,
            default_vault_name=_default_vault(),
        )
        result["rerank"] = "updated"
    else:
        await delete_rerank_config(workspace_id=workspace_id, config_pool=config_pool)
        result["rerank"] = "removed"

    # ── LLM ─────────────────────────────────────────────────────────────
    async with config_pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM workspace_llm_configs WHERE workspace_id = $1", workspace_id
        )
        if endpoint.llm is not None:
            await conn.execute(
                "INSERT INTO workspace_llm_configs "
                "(workspace_id, provider, model, base_url, api_key_ref, "
                "rpm_limit, tpm_limit) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                workspace_id,
                endpoint.llm.provider,
                endpoint.llm.model,
                endpoint.llm.base_url,
                endpoint.llm.api_key_ref,
                endpoint.llm.rpm_limit,
                endpoint.llm.tpm_limit,
            )
            result["llm"] = "updated"
        else:
            result["llm"] = "removed"

    log.info(
        "workspace.refreshed_from_endpoint",
        workspace=workspace_name,
        indexer=result["indexer"],
        rerank=result["rerank"],
        llm=result["llm"],
    )
    return result
