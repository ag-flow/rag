from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any, Protocol

import asyncpg
import structlog

from rag.db.helpers import fetch_one

log = structlog.get_logger(__name__)

_VAULT_REF_TMPL = "${vault://%s:/%s}"


class _VaultSvc(Protocol):
    async def get_by_name(self, conn: asyncpg.Connection, name: str) -> Any | None: ...


class _ClientProvider(Protocol):
    async def get_client(self, key: str) -> Any: ...
    async def get_default_vault_name(self) -> str | None: ...


class WebhookAlreadyEnabledError(Exception):
    def __init__(self, workspace: str, source: str) -> None:
        super().__init__(f"Webhook already enabled on {workspace}/{source}")


class WebhookNotEnabledError(Exception):
    def __init__(self, workspace: str, source: str) -> None:
        super().__init__(f"Webhook not enabled on {workspace}/{source}")


def _build_harpo_path(workspace_name: str, source_name: str) -> str:
    return f"sources/{workspace_name}/{source_name}/webhook_secret"


def _build_vault_ref(vault_name: str, workspace_name: str, source_name: str) -> str:
    path = _build_harpo_path(workspace_name, source_name)
    return _VAULT_REF_TMPL % (vault_name, path)


async def enable_webhook(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    source_name: str,
    vault_svc: _VaultSvc,
    client_provider: _ClientProvider,
) -> str:
    """Active le mode webhook sur la source. Retourne le secret en clair (une seule fois)."""
    row = await fetch_one(
        conn,
        """
        SELECT ws.id, ws.config, ws.webhook_enabled
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1 AND ws.name = $2
        """,
        workspace_name,
        source_name,
    )
    if row is None:
        raise ValueError(f"Source {source_name!r} not found in workspace {workspace_name!r}")
    if row["webhook_enabled"]:
        raise WebhookAlreadyEnabledError(workspace_name, source_name)

    vault_name = await client_provider.get_default_vault_name()
    if vault_name is None:
        raise RuntimeError("No default Harpocrate vault configured")

    vault = await vault_svc.get_by_name(conn, vault_name)
    if vault is None:
        raise RuntimeError(f"Vault {vault_name!r} not found")

    secret = secrets.token_hex(32)
    harpo_path = _build_harpo_path(workspace_name, source_name)
    client = await client_provider.get_client(str(vault.api_key_id))
    await asyncio.to_thread(client.set_secret, harpo_path, secret)

    vault_ref = _build_vault_ref(vault_name, workspace_name, source_name)

    raw = row["config"]
    config = json.loads(raw) if isinstance(raw, str) else dict(raw)
    config["webhook_secret_ref"] = vault_ref

    await conn.execute(
        """
        UPDATE workspace_sources
        SET config = $1::jsonb,
            webhook_enabled = true,
            next_sync_at = NULL
        WHERE id = $2
        """,
        json.dumps(config),
        row["id"],
    )
    log.info("source.webhook.enabled", workspace=workspace_name, source=source_name)
    return secret


async def disable_webhook(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    source_name: str,
    vault_svc: _VaultSvc,
    client_provider: _ClientProvider,
) -> None:
    """Desactive le mode webhook. Supprime le secret dans Harpocrate et relance le scheduler."""
    row = await fetch_one(
        conn,
        """
        SELECT ws.id, ws.config, ws.webhook_enabled
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1 AND ws.name = $2
        """,
        workspace_name,
        source_name,
    )
    if row is None:
        raise ValueError(f"Source {source_name!r} not found in workspace {workspace_name!r}")
    if not row["webhook_enabled"]:
        raise WebhookNotEnabledError(workspace_name, source_name)

    raw = row["config"]
    config = json.loads(raw) if isinstance(raw, str) else dict(raw)

    vault_ref: str | None = config.pop("webhook_secret_ref", None)
    if vault_ref:
        vault_name = await client_provider.get_default_vault_name()
        if vault_name:
            vault = await vault_svc.get_by_name(conn, vault_name)
            if vault:
                harpo_path = _build_harpo_path(workspace_name, source_name)
                client = await client_provider.get_client(str(vault.api_key_id))
                try:
                    await asyncio.to_thread(client.delete_secret, harpo_path)
                except Exception:
                    log.warning("source.webhook.delete_secret_failed", path=harpo_path)

    await conn.execute(
        """
        UPDATE workspace_sources
        SET config = $1::jsonb,
            webhook_enabled = false,
            next_sync_at = now()
        WHERE id = $2
        """,
        json.dumps(config),
        row["id"],
    )
    log.info("source.webhook.disabled", workspace=workspace_name, source=source_name)


async def rotate_webhook_secret(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    source_name: str,
    vault_svc: _VaultSvc,
    client_provider: _ClientProvider,
) -> str:
    """Genere un nouveau secret et l'ecrase dans Harpocrate. Retourne le secret en clair."""
    row = await fetch_one(
        conn,
        """
        SELECT ws.id, ws.config, ws.webhook_enabled
        FROM workspace_sources ws
        JOIN workspaces w ON w.id = ws.workspace_id
        WHERE w.name = $1 AND ws.name = $2
        """,
        workspace_name,
        source_name,
    )
    if row is None:
        raise ValueError(f"Source {source_name!r} not found in workspace {workspace_name!r}")
    if not row["webhook_enabled"]:
        raise WebhookNotEnabledError(workspace_name, source_name)

    vault_name = await client_provider.get_default_vault_name()
    if vault_name is None:
        raise RuntimeError("No default Harpocrate vault configured")
    vault = await vault_svc.get_by_name(conn, vault_name)
    if vault is None:
        raise RuntimeError(f"Vault {vault_name!r} not found")

    new_secret = secrets.token_hex(32)
    harpo_path = _build_harpo_path(workspace_name, source_name)
    client = await client_provider.get_client(str(vault.api_key_id))
    await asyncio.to_thread(client.set_secret, harpo_path, new_secret)

    log.info("source.webhook.secret_rotated", workspace=workspace_name, source=source_name)
    return new_secret
