from __future__ import annotations

from typing import Any, Protocol

import asyncpg
import structlog

from rag.api.errors import ReservedHeader, WebhookNotFound, WorkspaceNotFound
from rag.db.helpers import fetch_all, fetch_one
from rag.secrets.refs import build_ref

log = structlog.get_logger(__name__)

RESERVED_HEADERS: frozenset[str] = frozenset({
    "x-correlation-id",
    "x-rag-signature",
    "x-git-repo",
    "x-git-branch",
    "x-git-commit",
})

_RESERVED_LIST = sorted(RESERVED_HEADERS)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _check_reserved(header_name: str) -> None:
    if header_name.lower() in RESERVED_HEADERS:
        raise ReservedHeader(header_name, _RESERVED_LIST)


async def list_webhooks(
    config_pool: asyncpg.Pool,
    *,
    workspace_name: str,
) -> list[dict[str, Any]]:
    ws = await fetch_one(
        config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name
    )
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    hooks = await fetch_all(
        config_pool,
        "SELECT id, name, url, enabled FROM workspace_webhooks"
        " WHERE workspace_id=$1 ORDER BY created_at",
        ws["id"],
    )
    result = []
    for hook in hooks:
        headers = await _list_headers(config_pool, hook["id"])
        result.append({
            "id": str(hook["id"]),
            "name": hook["name"],
            "url": hook["url"],
            "enabled": hook["enabled"],
            "headers": headers,
        })
    return result


async def _list_headers(
    config_pool: asyncpg.Pool, webhook_id: Any
) -> list[dict[str, Any]]:
    rows = await fetch_all(
        config_pool,
        "SELECT id, name, vault_ref, enabled FROM webhook_headers WHERE webhook_id=$1 ORDER BY id",
        webhook_id,
    )
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "value": None,
            "vault_ref": r["vault_ref"],
            "enabled": r["enabled"],
        }
        for r in rows
    ]


async def create_webhook(
    config_pool: asyncpg.Pool,
    *,
    workspace_name: str,
    name: str,
    url: str,
    enabled: bool,
    headers: list[dict[str, Any]],
    resolver: _ResolverProtocol | None,
) -> dict[str, Any]:
    for h in headers:
        _check_reserved(h["name"])

    ws = await fetch_one(
        config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name
    )
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    async with config_pool.acquire() as conn, conn.transaction():
        wh_id = await conn.fetchval(
            "INSERT INTO workspace_webhooks (workspace_id, name, url, enabled) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            ws["id"], name, url, enabled,
        )
        saved_headers = []
        for h in headers:
            vault_ref, value_to_store = await _resolve_header_write(
                wh_id=str(wh_id),
                workspace_name=workspace_name,
                header_name=h["name"],
                value=h.get("value"),
                vault=h.get("vault"),
                resolver=resolver,
            )
            hdr_id = await conn.fetchval(
                "INSERT INTO webhook_headers (webhook_id, name, value, vault_ref, enabled) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                wh_id, h["name"], value_to_store, vault_ref, h.get("enabled", True),
            )
            saved_headers.append({
                "id": str(hdr_id),
                "name": h["name"],
                "value": None,
                "vault_ref": vault_ref,
                "enabled": h.get("enabled", True),
            })

    log.info("webhook.created", workspace=workspace_name, name=name, webhook_id=str(wh_id))
    return {
        "id": str(wh_id), "name": name, "url": url, "enabled": enabled, "headers": saved_headers
    }


async def _resolve_header_write(
    *,
    wh_id: str,
    workspace_name: str,
    header_name: str,
    value: str | None,
    vault: str | None,
    resolver: _ResolverProtocol | None,
) -> tuple[str | None, str | None]:
    """Retourne (vault_ref, value_in_db). Si vault → build la ref, value_in_db=None."""
    if vault and value:
        logical = f"/workspaces/{workspace_name}/hooks/{wh_id}/headers/{header_name}"
        vault_ref = build_ref(vault, logical)
        return vault_ref, None
    return None, value


async def patch_webhook(
    config_pool: asyncpg.Pool,
    *,
    webhook_id: str,
    name: str | None = None,
    url: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    sets = []
    params: list[Any] = []
    idx = 1
    if name is not None:
        sets.append(f"name=${idx}")
        params.append(name)
        idx += 1
    if url is not None:
        sets.append(f"url=${idx}")
        params.append(url)
        idx += 1
    if enabled is not None:
        sets.append(f"enabled=${idx}")
        params.append(enabled)
        idx += 1

    if not sets:
        row = await fetch_one(
            config_pool,
            "SELECT id, name, url, enabled FROM workspace_webhooks WHERE id=$1::uuid",
            webhook_id,
        )
    else:
        params.append(webhook_id)
        row = await fetch_one(
            config_pool,
            f"UPDATE workspace_webhooks SET {', '.join(sets)} WHERE id=${idx}::uuid "  # noqa: S608
            "RETURNING id, name, url, enabled",
            *params,
        )
    if row is None:
        raise WebhookNotFound(webhook_id)
    headers = await _list_headers(config_pool, row["id"])
    return {"id": str(row["id"]), "name": row["name"], "url": row["url"],
            "enabled": row["enabled"], "headers": headers}


async def delete_webhook(
    config_pool: asyncpg.Pool,
    *,
    webhook_id: str,
    resolver: _ResolverProtocol | None,
) -> None:
    row = await fetch_one(
        config_pool,
        "SELECT id FROM workspace_webhooks WHERE id=$1::uuid",
        webhook_id,
    )
    if row is None:
        raise WebhookNotFound(webhook_id)

    vault_headers = await fetch_all(
        config_pool,
        "SELECT vault_ref FROM webhook_headers WHERE webhook_id=$1 AND vault_ref IS NOT NULL",
        row["id"],
    )
    if vault_headers and resolver is not None:
        for h in vault_headers:
            log.warning("webhook.delete_vault_ref_orphan", vault_ref=h["vault_ref"])

    await config_pool.execute(
        "DELETE FROM workspace_webhooks WHERE id=$1", row["id"]
    )
    log.info("webhook.deleted", webhook_id=webhook_id)


async def patch_webhook_header(
    config_pool: asyncpg.Pool,
    *,
    webhook_id: str,
    header_id: str,
    value: str | None = None,
    vault: str | None = None,
    enabled: bool | None = None,
    workspace_name: str,
    resolver: _ResolverProtocol | None,
) -> dict[str, Any]:
    row = await fetch_one(
        config_pool,
        "SELECT wh.id, wh.name, wh.vault_ref FROM webhook_headers wh "
        "JOIN workspace_webhooks w ON w.id = wh.webhook_id "
        "WHERE wh.id=$1::uuid AND w.id=$2::uuid",
        header_id, webhook_id,
    )
    if row is None:
        raise WebhookNotFound(header_id)

    _check_reserved(row["name"])

    sets = []
    params: list[Any] = []
    idx = 1

    if value is not None:
        if row["vault_ref"] and resolver is not None:
            log.info("webhook.header_update_vault", header_id=header_id)
        else:
            sets.append(f"value=${idx}")
            params.append(value)
            idx += 1

    if enabled is not None:
        sets.append(f"enabled=${idx}")
        params.append(enabled)
        idx += 1

    if sets:
        params.append(header_id)
        await config_pool.execute(
            f"UPDATE webhook_headers SET {', '.join(sets)} WHERE id=${idx}::uuid",  # noqa: S608
            *params,
        )

    updated = await fetch_one(
        config_pool,
        "SELECT id, name, vault_ref, enabled FROM webhook_headers WHERE id=$1::uuid",
        header_id,
    )
    return {
        "id": str(updated["id"]),  # type: ignore[index]
        "name": updated["name"],  # type: ignore[index]
        "value": None,
        "vault_ref": updated["vault_ref"],  # type: ignore[index]
        "enabled": updated["enabled"],  # type: ignore[index]
    }


async def list_webhook_calls(
    config_pool: asyncpg.Pool,
    *,
    workspace_name: str,
    webhook_id: str | None = None,
    correlation_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ws = await fetch_one(
        config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name
    )
    if ws is None:
        raise WorkspaceNotFound(workspace_name)

    conditions = ["wc.workspace_id=$1"]
    params: list[Any] = [ws["id"]]
    idx = 2

    if webhook_id:
        conditions.append(f"wc.webhook_id=${idx}::uuid")
        params.append(webhook_id)
        idx += 1
    if correlation_id:
        conditions.append(f"wc.correlation_id=${idx}")
        params.append(correlation_id)
        idx += 1
    if status_filter == "success":
        conditions.append("wc.http_status BETWEEN 200 AND 299")
    elif status_filter == "error":
        conditions.append("(wc.http_status IS NULL OR wc.http_status NOT BETWEEN 200 AND 299)")

    params.append(limit)
    where = " AND ".join(conditions)
    rows = await fetch_all(
        config_pool,
        f"""
        SELECT wc.id, wc.webhook_id, wh.name AS webhook_name,
               wc.correlation_id, wc.triggered_by, wc.webhook_url,
               wc.http_status, wc.error, wc.duration_ms, wc.called_at
        FROM webhook_calls wc
        JOIN workspace_webhooks wh ON wh.id = wc.webhook_id
        WHERE {where}
        ORDER BY wc.called_at DESC
        LIMIT ${idx}
        """,  # noqa: S608
        *params,
    )
    return [
        {
            "id": str(r["id"]),
            "webhook_id": str(r["webhook_id"]),
            "webhook_name": r["webhook_name"],
            "correlation_id": r["correlation_id"],
            "triggered_by": r["triggered_by"],
            "webhook_url": r["webhook_url"],
            "http_status": r["http_status"],
            "error": r["error"],
            "duration_ms": r["duration_ms"],
            "called_at": r["called_at"].isoformat(),
            "success": r["http_status"] is not None and 200 <= r["http_status"] <= 299,
        }
        for r in rows
    ]


async def purge_old_webhook_calls(config_pool: asyncpg.Pool) -> None:
    await config_pool.execute(
        "DELETE FROM webhook_calls WHERE called_at < now() - interval '24 hours'"
    )
