from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.api.errors import (
    SourceNotFound,
    SourceTypeNotSupported,
    VaultNotFoundForWorkspace,
    WorkspaceNotFound,
)
from rag.db.helpers import fetch_all, fetch_one
from rag.schemas.admin import SourceCreateRequest, SourceUpdateRequest
from rag.secrets.refs import build_ref
from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


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
    harpocrate_vaults_service: HarpocrateVaultsService,
) -> dict[str, Any]:
    """Crée une source pour un workspace.

    Si `auth_value` est fourni, stocke la clé dans Harpocrate sous
    ``<workspace_name>/<source_name>/auth`` et construit la ref dans config.
    """
    if request.type != "git":
        raise SourceTypeNotSupported(request.type)

    ws_id = await _get_workspace_id_or_raise(config_pool, workspace_name)

    config = dict(request.config)
    auth_path: str | None = None

    if request.auth_value:
        async with config_pool.acquire() as conn:
            vault = await harpocrate_vaults_service.get_by_name(conn, request.api_key_vault)
        if vault is None:
            raise VaultNotFoundForWorkspace(request.api_key_vault)
        auth_path = f"{workspace_name}/{request.name}/auth"
        async with config_pool.acquire() as conn:
            await harpocrate_vaults_service.write_secret(
                conn,
                vault_name=request.api_key_vault,
                path=auth_path,
                value=request.auth_value,
            )
        config["auth_ref"] = build_ref(vault.api_key_id, auth_path)

    try:
        async with config_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workspace_sources (workspace_id, name, type, config, next_sync_at)
                VALUES ($1, $2, $3, $4::jsonb, now())
                RETURNING id, name, type, config, last_indexed_at, created_at
                """,
                ws_id,
                request.name,
                request.type,
                json.dumps(config),
            )
    except Exception:
        if auth_path is not None:
            async with config_pool.acquire() as conn:
                await harpocrate_vaults_service.delete_secret(
                    conn, vault_name=request.api_key_vault, path=auth_path
                )
        raise

    if row is None:
        raise RuntimeError("unexpected None from RETURNING")
    log.info("source.added", workspace=workspace_name, source_id=str(row["id"]))
    return _source_to_dict(row)


async def list_sources(config_pool: asyncpg.Pool, *, workspace_name: str) -> list[dict[str, Any]]:
    """Liste toutes les sources du workspace, plus récentes en premier."""
    rows = await fetch_all(
        config_pool,
        """
        SELECT ws.id, ws.name, ws.type, ws.config, ws.last_indexed_at, ws.created_at
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1
        ORDER BY ws.created_at DESC
        """,
        workspace_name,
    )
    return [_source_to_dict(r) for r in rows]


async def update_source(
    *,
    workspace_name: str,
    source_id: str,
    request: SourceUpdateRequest,
    config_pool: asyncpg.Pool,
    harpocrate_vaults_service: HarpocrateVaultsService,
) -> dict[str, Any]:
    """Met à jour la config d'une source.

    Lève SourceNotFound si l'id n'appartient pas au workspace.
    """
    ws_id = await _get_workspace_id_or_raise(config_pool, workspace_name)

    config = dict(request.config)

    if request.auth_value:
        # Récupère le nom et le vault actuels depuis la DB pour construire le path
        current = await fetch_one(
            config_pool,
            """
            SELECT ws.name, ws.config
            FROM workspace_sources ws
            WHERE ws.id = $1::uuid AND ws.workspace_id = $2
            """,
            source_id,
            ws_id,
        )
        if current is None:
            raise SourceNotFound(source_id)
        raw = current["config"]
        current_config = json.loads(raw) if isinstance(raw, str) else dict(raw)
        existing_ref: str | None = current_config.get("auth_ref")

        # Détermine le vault : priorité au vault explicitement fourni dans la requête
        source_name = current["name"] or source_id
        if request.api_key_vault:
            vault_name = request.api_key_vault
            auth_path = f"{workspace_name}/{source_name}/auth"
            existing_ref = None  # force recalcul de la ref
        elif existing_ref:
            from rag.secrets.refs import parse_ref
            vault_api_key_id, auth_path = parse_ref(existing_ref)
            async with config_pool.acquire() as conn:
                vault = await harpocrate_vaults_service.get_by_api_key_id(conn, vault_api_key_id)
            vault_name = vault.name if vault else None
        else:
            vault_name = None
            auth_path = f"{workspace_name}/{source_name}/auth"

        if vault_name:
            async with config_pool.acquire() as conn:
                await harpocrate_vaults_service.write_secret(
                    conn,
                    vault_name=vault_name,
                    path=auth_path,
                    value=request.auth_value,
                )
            if existing_ref:
                config["auth_ref"] = existing_ref
            else:
                async with config_pool.acquire() as conn:
                    vault_obj = await harpocrate_vaults_service.get_by_name(conn, vault_name)
                if vault_obj:
                    config["auth_ref"] = build_ref(vault_obj.api_key_id, auth_path)

    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workspace_sources SET config = $1::jsonb
            WHERE id = $2::uuid AND workspace_id = $3
            RETURNING id, name, type, config, last_indexed_at, created_at
            """,
            json.dumps(config),
            source_id,
            ws_id,
        )
    if row is None:
        raise SourceNotFound(source_id)
    log.info("source.updated", workspace=workspace_name, source_id=source_id)
    return _source_to_dict(row)


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
        "name": row["name"],
        "type": row["type"],
        "config": config,
        "last_indexed_at": last.isoformat() if last is not None else None,
        "created_at": row["created_at"].isoformat(),
    }
