from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.admin import RerankSpec
from rag.secrets.refs import build_ref, is_vault_ref

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _to_vault_ref(logical_key: str, vault_name: str) -> str:
    return build_ref(vault_name, logical_key)


async def get_rerank_config(
    workspace_id: UUID | str,
    config_pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Retourne la config rerank du workspace ou None si absente."""
    row = await config_pool.fetchrow(
        """
        SELECT workspace_id, provider, model, base_url, api_key_ref,
               top_k_pre_rerank, created_at, updated_at
        FROM rerank_configs
        WHERE workspace_id = $1
        """,
        workspace_id,
    )
    return dict(row) if row is not None else None


async def upsert_rerank_config(
    *,
    workspace_id: UUID | str,
    spec: RerankSpec,
    config_pool: asyncpg.Pool,
    resolver: _ResolverProtocol,
    default_vault_name: str,
) -> dict[str, Any]:
    """Insert ou update la config rerank. Validation eager api_key_ref si défini.

    Lève l'exception du resolver si la ref n'est pas résolvable (aucune row écrite).
    """
    if spec.api_key_ref:
        # Eager validation : si la ref n'est pas résolvable, on lève AVANT d'écrire.
        # Si api_key_ref est déjà un vault_ref complet (harpo_path), l'utiliser directement.
        ref_to_validate = (
            spec.api_key_ref
            if is_vault_ref(spec.api_key_ref)
            else _to_vault_ref(spec.api_key_ref, default_vault_name)
        )
        await resolver.resolve_with_retry(ref_to_validate)

    row = await config_pool.fetchrow(
        """
        INSERT INTO rerank_configs
            (workspace_id, provider, model, base_url, api_key_ref, top_k_pre_rerank)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (workspace_id) DO UPDATE
        SET provider = EXCLUDED.provider,
            model = EXCLUDED.model,
            base_url = EXCLUDED.base_url,
            api_key_ref = EXCLUDED.api_key_ref,
            top_k_pre_rerank = EXCLUDED.top_k_pre_rerank,
            updated_at = now()
        RETURNING workspace_id, provider, model, base_url, api_key_ref,
                  top_k_pre_rerank, created_at, updated_at
        """,
        workspace_id, spec.provider, spec.model, spec.base_url,
        spec.api_key_ref, spec.top_k_pre_rerank,
    )
    if row is None:
        raise RuntimeError("unexpected None from RETURNING")
    log.info(
        "rerank.upserted",
        workspace_id=str(workspace_id),
        provider=spec.provider,
        model=spec.model,
    )
    return dict(row)


async def delete_rerank_config(
    workspace_id: UUID | str,
    config_pool: asyncpg.Pool,
) -> None:
    """Idempotent : pas d'erreur si la config n'existe pas."""
    await config_pool.execute(
        "DELETE FROM rerank_configs WHERE workspace_id = $1",
        workspace_id,
    )
    log.info("rerank.deleted", workspace_id=str(workspace_id))
