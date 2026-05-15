from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.api.errors import (
    RefNotFoundInVault,
    SourceNotFound,
    SourceTypeNotSupported,
    VaultUnreachable,
    WorkspaceNotFound,
)
from rag.db.helpers import fetch_all, fetch_one
from rag.schemas.admin import SourceCreateRequest
from rag.secrets.resolver import VaultLookupFailed

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


def _to_vault_ref(logical_key: str, *, vault_id: str = "rag") -> str:
    return f"${{vault://{vault_id}:{logical_key}}}"


def _validate_ref_via_vault(resolver: _ResolverProtocol, logical_key: str) -> None:
    try:
        resolver.resolve_with_retry(_to_vault_ref(logical_key))
    except VaultLookupFailed as e:
        raise RefNotFoundInVault(logical_key) from e
    except (ConnectionError, TimeoutError) as e:
        raise VaultUnreachable() from e


async def _get_workspace_id_or_raise(config_pool: asyncpg.Pool, name: str) -> UUID:
    row = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name=$1", name)
    if row is None:
        raise WorkspaceNotFound(name)
    return UUID(str(row["id"]))


async def add_source(
    *,
    workspace_name: str,
    request: SourceCreateRequest,
    config_pool: asyncpg.Pool,
    resolver: _ResolverProtocol,
) -> dict[str, Any]:
    """Crée une source pour un workspace. Eager validation `auth_ref` si présente.

    Lève WorkspaceNotFound, RefNotFoundInVault, VaultUnreachable,
    SourceTypeNotSupported (le schema Pydantic Literal['git'] couvre déjà ça,
    mais la classe d'erreur reste utile pour les sources ajoutées par worker M3+).
    """
    if request.type != "git":
        raise SourceTypeNotSupported(request.type)

    ws_id = await _get_workspace_id_or_raise(config_pool, workspace_name)

    auth_ref = request.config.get("auth_ref")
    if auth_ref:
        _validate_ref_via_vault(resolver, auth_ref)

    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO workspace_sources (workspace_id, type, config)
            VALUES ($1, $2, $3::jsonb)
            RETURNING id, type, config, last_indexed_at, created_at
            """,
            ws_id,
            request.type,
            json.dumps(request.config),
        )

    if row is None:
        raise RuntimeError("unexpected None from RETURNING")
    log.info("source.added", workspace=workspace_name, source_id=str(row["id"]))
    return _source_to_dict(row)


async def list_sources(config_pool: asyncpg.Pool, *, workspace_name: str) -> list[dict[str, Any]]:
    """Liste toutes les sources du workspace, plus récentes en premier."""
    rows = await fetch_all(
        config_pool,
        """
        SELECT ws.id, ws.type, ws.config, ws.last_indexed_at, ws.created_at
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1
        ORDER BY ws.created_at DESC
        """,
        workspace_name,
    )
    return [_source_to_dict(r) for r in rows]


async def delete_source(*, workspace_name: str, source_id: str, config_pool: asyncpg.Pool) -> None:
    """Supprime une source. Lève SourceNotFound si l'id n'appartient pas au workspace."""
    await _get_workspace_id_or_raise(config_pool, workspace_name)
    async with config_pool.acquire() as conn:
        tag = await conn.execute(
            """
            DELETE FROM workspace_sources
            WHERE id = $1::uuid
              AND workspace_id = (SELECT id FROM workspaces WHERE name=$2)
            """,
            source_id,
            workspace_name,
        )
    if tag == "DELETE 0":
        raise SourceNotFound(source_id)
    log.info("source.deleted", workspace=workspace_name, source_id=source_id)


def _source_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    raw_config = row["config"]
    config = json.loads(raw_config) if isinstance(raw_config, str) else dict(raw_config)
    last = row["last_indexed_at"]
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "config": config,
        "last_indexed_at": last.isoformat() if last is not None else None,
        "created_at": row["created_at"].isoformat(),
    }
