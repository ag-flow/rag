from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog
from fastapi import HTTPException, status

from rag.api.errors import (
    SourceNotFound,
    SourceTypeNotSupported,
    WorkspaceNotFound,
)
from rag.db.helpers import fetch_all, fetch_one
from rag.schemas.admin import SourceCreateRequest, SourceUpdateRequest
from rag.secrets.refs import is_vault_ref
from rag.services.harpocrate_vaults import HarpocrateVaultsService
from rag.sync.git_ops import detect_default_branch

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


async def _get_workspace_id_or_raise(config_pool: asyncpg.Pool, name: str) -> UUID:
    row = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name=$1", name)
    if row is None:
        raise WorkspaceNotFound(name)
    return UUID(str(row["id"]))


async def _resolve_branch_for_write(
    config: dict[str, Any], *, token: str | None
) -> tuple[dict[str, Any], str | None]:
    """Garantit une branche concrète dans `config`.

    - Branche déjà fournie (non vide) → inchangée, pas d'avertissement.
    - Branche vide/absente → détecte la branche par défaut du remote.
      Détection OK → branche détectée. Échec → repli "main" + avertissement.

    Retourne (config copié avec branche résolue, message d'avertissement | None).
    Ne mute pas le dict d'entrée.
    """
    config = dict(config)
    if config.get("branch"):
        return config, None
    detected = await detect_default_branch(url=config.get("url", ""), token=token)
    if detected:
        config["branch"] = detected
        return config, None
    config["branch"] = "main"
    log.warning("source.branch_detect_failed", url=config.get("url", ""))
    return config, "Branche par défaut non détectée, repli sur 'main'."


async def _assert_ref_accessible(
    conn: asyncpg.Connection,
    *,
    harpo_path: str,
    owner_id: str,
) -> None:
    """Vérifie qu'un harpo_path appartient à un vault accessible à owner_id (IDOR guard)."""
    count = await conn.fetchval(
        """
        SELECT count(*) FROM (
            SELECT v.owner_id, v.is_default FROM git_credentials gc
            JOIN harpocrate_vaults v ON v.id = gc.vault_id
            WHERE gc.harpo_path = $1
            UNION ALL
            SELECT v.owner_id, v.is_default FROM ssh_keys sk
            JOIN harpocrate_vaults v ON v.id = sk.vault_id
            WHERE sk.harpo_path = $1
        ) creds
        WHERE is_default = true OR owner_id = $2
        """,
        harpo_path,
        owner_id,
    )
    if (count or 0) == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="credential not accessible",
        )


async def add_source(
    *,
    workspace_name: str,
    request: SourceCreateRequest,
    config_pool: asyncpg.Pool,
    harpocrate_vaults_service: HarpocrateVaultsService,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """Crée une source pour un workspace.

    Les champs d'authentification (auth_ref, ssh_key_ref, ssh_username,
    git_provider, auth_type) sont stockés directement dans le config JSONB.
    Le credential existe déjà dans Harpocrate ; on ne l'écrit plus ici.
    """
    if request.type != "git":
        raise SourceTypeNotSupported(request.type)

    ws_id = await _get_workspace_id_or_raise(config_pool, workspace_name)
    config = dict(request.config)

    if request.git_provider:
        config["git_provider"] = request.git_provider
    if request.auth_type:
        config["auth_type"] = request.auth_type
    if request.auth_ref:
        if owner_id:
            async with config_pool.acquire() as conn:
                await _assert_ref_accessible(conn, harpo_path=request.auth_ref, owner_id=owner_id)
        config["auth_ref"] = request.auth_ref
    if request.ssh_key_ref:
        if owner_id:
            async with config_pool.acquire() as conn:
                await _assert_ref_accessible(
                    conn, harpo_path=request.ssh_key_ref, owner_id=owner_id
                )
        config["ssh_key_ref"] = request.ssh_key_ref
    if request.ssh_username:
        config["ssh_username"] = request.ssh_username

    # Pour detect_default_branch : token None si SSH (fallback "main" acceptable)
    config, branch_warning = await _resolve_branch_for_write(config, token=None)

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

    if row is None:
        raise RuntimeError("unexpected None from RETURNING")
    log.info("source.added", workspace=workspace_name, source_id=str(row["id"]))
    result = _source_to_dict(row)
    result["branch_warning"] = branch_warning
    return result


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
    resolver: _ResolverProtocol,
) -> dict[str, Any]:
    """Met à jour la config d'une source.

    Les champs d'authentification sont préservés depuis le config actuel si
    non fournis dans la requête. Aucune écriture dans Harpocrate.
    Lève SourceNotFound si l'id n'appartient pas au workspace.
    """
    ws_id = await _get_workspace_id_or_raise(config_pool, workspace_name)

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

    config = dict(request.config)

    # Préserver les champs auth existants si non fournis dans la requête
    for field in ("git_provider", "auth_type", "auth_ref", "ssh_key_ref", "ssh_username"):
        new_val = getattr(request, field, None)
        if new_val is not None:
            config[field] = new_val
        elif field in current_config:
            config[field] = current_config[field]

    config, branch_warning = await _resolve_branch_for_write(config, token=None)

    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workspace_sources
            SET config = $1::jsonb
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
    result = _source_to_dict(row)
    result["branch_warning"] = branch_warning
    return result


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


async def test_source_connection(
    *,
    workspace_name: str,
    source_id: str,
    config_pool: asyncpg.Pool,
    resolver: _ResolverProtocol,
) -> dict[str, Any]:
    """Teste la connexion git d'une source via son auth_ref résolu.

    Retourne ``{success: bool, message: str | None}``.
    """
    row = await fetch_one(
        config_pool,
        """
        SELECT ws.config, ws.name
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE ws.id = $1::uuid AND w.name = $2
        """,
        source_id,
        workspace_name,
    )
    if row is None:
        raise SourceNotFound(source_id)

    raw = row["config"]
    config = json.loads(raw) if isinstance(raw, str) else dict(raw)
    url: str = config.get("url", "")
    auth_ref: str | None = config.get("auth_ref")

    token: str | None = None
    if auth_ref:
        if is_vault_ref(auth_ref):
            token = await resolver.resolve_with_retry(auth_ref)
        else:
            log.warning("test_connection.legacy_auth_ref", source_id=source_id)

    if token:
        parsed = urllib.parse.urlparse(url)
        authed_url = parsed._replace(
            netloc=f"x-token-auth:{urllib.parse.quote(token, safe='')}@{parsed.hostname}"
            + (f":{parsed.port}" if parsed.port else "")
        ).geturl()
    else:
        authed_url = url

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            "--heads",
            authed_url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        _, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            return {"success": True, "message": None}
        stderr_msg = stderr_bytes.decode(errors="replace").strip()
        return {"success": False, "message": stderr_msg[:300] or "git ls-remote a échoué"}
    except TimeoutError:
        return {"success": False, "message": "Délai dépassé (15 s)"}
    except Exception as exc:
        return {"success": False, "message": str(exc)[:300]}


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
