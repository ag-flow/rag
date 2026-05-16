from __future__ import annotations

from typing import Any, Protocol

import asyncpg
import structlog

from rag.api.errors import (
    IndexerChangeRequiresReindex,
    RefNotFoundInVault,
    VaultUnreachable,
    WorkspaceNotFound,
)
from rag.db.helpers import fetch_all, fetch_one
from rag.db.workspace_schema import (
    create_embeddings_table,
    derive_workspace_dsn,
)
from rag.schemas.admin import IndexerSpec
from rag.secrets.refs import build_ref
from rag.secrets.resolver import VaultLookupFailed
from rag.services.models import get_dimension_or_raise

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


async def create_pending_job(
    *, workspace_name: str, triggered_by: str, config_pool: asyncpg.Pool
) -> dict[str, Any]:
    """Insère un job en status 'pending' pour le workspace.

    `triggered_by` ∈ {'manual', 'webhook', 'push', 'schedule', 'reindex_indexer_change'}.
    La validité est vérifiée par la CHECK constraint en base (migration 003).
    """
    row = await fetch_one(
        config_pool,
        """
        INSERT INTO index_jobs (workspace_id, triggered_by, status)
        SELECT id, $2, 'pending' FROM workspaces WHERE name = $1
        RETURNING id, triggered_by, status, files_changed, files_skipped,
                  error_message, started_at, finished_at, duration_ms
        """,
        workspace_name,
        triggered_by,
    )
    if row is None:
        raise WorkspaceNotFound(workspace_name)

    log.info("job.created_pending", workspace=workspace_name, triggered_by=triggered_by)
    return _job_to_dict(row)


async def list_jobs(config_pool: asyncpg.Pool, *, workspace_name: str) -> list[dict[str, Any]]:
    """Historique des jobs pour un workspace, plus récents en premier (started_at DESC).

    Lève WorkspaceNotFound si le workspace n'existe pas.
    """
    ws = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name)
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    rows = await fetch_all(
        config_pool,
        """
        SELECT id, triggered_by, status, files_changed, files_skipped,
               error_message, started_at, finished_at, duration_ms
        FROM index_jobs
        WHERE workspace_id = $1
        ORDER BY started_at DESC NULLS LAST, id DESC
        """,
        ws["id"],
    )
    return [_job_to_dict(r) for r in rows]


def _job_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "triggered_by": row["triggered_by"],
        "status": row["status"],
        "files_changed": int(row["files_changed"] or 0),
        "files_skipped": int(row["files_skipped"] or 0),
        "error_message": row["error_message"],
        "started_at": row["started_at"].isoformat() if row["started_at"] else None,
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "duration_ms": row["duration_ms"],
    }


def _to_vault_ref(logical_key: str, vault_name: str) -> str:
    """Construit une ref ``${vault://<vault_name>:<logical>}`` dynamique."""
    return build_ref(vault_name, logical_key)


async def _validate_ref_via_vault(
    resolver: _ResolverProtocol,
    logical_key: str,
    vault_name: str,
) -> None:
    try:
        await resolver.resolve_with_retry(_to_vault_ref(logical_key, vault_name))
    except VaultLookupFailed as e:
        raise RefNotFoundInVault(logical_key) from e
    except (ConnectionError, TimeoutError) as e:
        raise VaultUnreachable() from e


async def reindex_workspace(
    *,
    name: str,
    new_indexer: IndexerSpec | None,
    confirm: bool,
    config_pool: asyncpg.Pool,
    admin_dsn: str,
    resolver: _ResolverProtocol,
    default_vault_name: str = "rag",
) -> dict[str, Any]:
    """Crée un job pending. Si new_indexer diffère du courant → flow de changement.

    Cf. design 2026-05-15-M2-api-admin-design.md, Flow C.
    """
    row = await fetch_one(
        config_pool,
        """
        SELECT w.id AS workspace_id, w.rag_base,
               ic.provider, ic.model, ic.api_key_ref, ic.dimension
        FROM workspaces w
        LEFT JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise WorkspaceNotFound(name)

    same_indexer = new_indexer is None or (
        new_indexer.provider == row["provider"]
        and new_indexer.model == row["model"]
        and (new_indexer.api_key_ref or None) == (row["api_key_ref"] or None)
    )
    if same_indexer:
        return await create_pending_job(
            workspace_name=name, triggered_by="manual", config_pool=config_pool
        )

    # Changement d'indexeur
    if new_indexer is None:
        raise RuntimeError("unexpected: new_indexer should not be None here")
    new_dimension = await get_dimension_or_raise(
        config_pool, provider=new_indexer.provider, model=new_indexer.model
    )
    if new_indexer.api_key_ref is not None:
        await _validate_ref_via_vault(resolver, new_indexer.api_key_ref, default_vault_name)

    documents_count = await fetch_one(
        config_pool,
        "SELECT COUNT(*) AS c FROM indexed_documents WHERE workspace_id=$1",
        row["workspace_id"],
    )
    docs = int(documents_count["c"]) if documents_count else 0

    if docs > 0 and not confirm:
        raise IndexerChangeRequiresReindex(
            workspace=name,
            current=f"{row['provider']}/{row['model']} (dim={row['dimension']})",
            requested=f"{new_indexer.provider}/{new_indexer.model} (dim={new_dimension})",
            documents_count=docs,
        )

    # Drop + recreate la table embeddings avec la nouvelle dimension
    ws_dsn = derive_workspace_dsn(admin_dsn, row["rag_base"])
    drop_conn = await asyncpg.connect(ws_dsn)
    try:
        await drop_conn.execute("DROP TABLE IF EXISTS embeddings CASCADE")
    finally:
        await drop_conn.close()
    await create_embeddings_table(ws_dsn, dimension=new_dimension)

    # Update config + invalidate documents
    async with config_pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM indexed_documents WHERE workspace_id=$1",
            row["workspace_id"],
        )
        await conn.execute(
            """
            UPDATE indexer_configs
            SET provider=$1, model=$2, api_key_ref=$3, dimension=$4
            WHERE workspace_id=$5
            """,
            new_indexer.provider,
            new_indexer.model,
            new_indexer.api_key_ref,
            new_dimension,
            row["workspace_id"],
        )

    return await create_pending_job(
        workspace_name=name,
        triggered_by="reindex_indexer_change",
        config_pool=config_pool,
    )
