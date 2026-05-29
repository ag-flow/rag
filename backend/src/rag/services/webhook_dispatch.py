from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Protocol

import httpx
import structlog

from rag.db.helpers import fetch_all
from rag.services.webhook_validation import (
    validate_header_name,
    validate_header_value,
    validate_webhook_url,
)

log = structlog.get_logger(__name__)

_TIMEOUT = 10.0


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def _sign_payload(secret: str | None, payload_bytes: bytes) -> str | None:
    if secret is None:
        return None
    sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _build_payload(
    *,
    event: str,
    workspace: str,
    triggered_by: str,
    job_id: str,
    status: str,
    files_changed: int,
    files_skipped: int,
    duration_ms: int | None,
    finished_at: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    return {
        "event": event,
        "workspace": workspace,
        "triggered_by": triggered_by,
        "job_id": job_id,
        "status": status,
        "files_changed": files_changed,
        "files_skipped": files_skipped,
        "duration_ms": duration_ms,
        "finished_at": finished_at,
        "error_message": error_message,
    }


async def _async_validate_webhook_url(url: str) -> None:
    """Valide l'URL dans un executor pour ne pas bloquer la boucle asyncio."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, validate_webhook_url, url)


async def _http_post(url: str, *, headers: dict[str, str], content: bytes) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        return await client.post(url, content=content, headers=headers)


async def _insert_call(
    config_pool: Any,
    *,
    workspace_id: str,
    webhook_id: str,
    job_id: str,
    correlation_id: str,
    triggered_by: str,
    webhook_url: str,
    http_status: int | None,
    error: str | None,
    duration_ms: int,
) -> None:
    await config_pool.execute(
        """
        INSERT INTO webhook_calls
            (workspace_id, webhook_id, job_id, correlation_id, triggered_by,
             webhook_url, http_status, error, duration_ms)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9)
        """,
        workspace_id, webhook_id, job_id, correlation_id, triggered_by,
        webhook_url, http_status, error, duration_ms,
    )


async def _call_one_webhook(
    *,
    webhook: dict[str, Any],
    raw_headers: list[dict[str, Any]],
    payload_bytes: bytes,
    correlation_id: str,
    triggered_by: str,
    git_repo: str | None,
    git_branch: str | None,
    git_commit: str | None,
    signature: str | None,
    config_pool: Any,
    workspace_id: str,
    job_id: str,
    resolver: _ResolverProtocol | None,
) -> None:
    wh_id = str(webhook["id"])
    url = webhook["url"]

    # Validation SSRF — re-vérifiée au dispatch (défense en profondeur,
    # protection contre DNS rebinding entre la sauvegarde et l'appel).
    try:
        await _async_validate_webhook_url(url)
    except ValueError as exc:
        log.warning("webhook.ssrf_rejected", url=url, wh_id=wh_id, reason=str(exc))
        await _insert_call(
            config_pool,
            workspace_id=workspace_id,
            webhook_id=wh_id,
            job_id=job_id,
            correlation_id=correlation_id,
            triggered_by=triggered_by,
            webhook_url=url,
            http_status=None,
            error=f"ssrf_rejected: {exc}",
            duration_ms=0,
        )
        return

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
    }
    if signature:
        headers["X-RAG-Signature"] = signature
    if git_repo:
        headers["X-Git-Repo"] = git_repo
    if git_branch:
        headers["X-Git-Branch"] = git_branch
    if git_commit:
        headers["X-Git-Commit"] = git_commit

    # Résout et valide les headers custom
    for h in raw_headers:
        if not h.get("enabled"):
            continue
        name: str = h["name"]
        try:
            validate_header_name(name)
        except ValueError:
            log.warning("webhook.invalid_header_name_skipped", name=name, wh_id=wh_id)
            continue

        vault_ref = h.get("vault_ref")
        if vault_ref and resolver is not None:
            try:
                val = await resolver.resolve_with_retry(vault_ref)
                validate_header_value(val)
                headers[name] = val
            except ValueError:
                log.warning("webhook.invalid_header_value_skipped", name=name, wh_id=wh_id)
            except Exception:
                log.warning("webhook.header_resolve_failed", name=name, wh_id=wh_id)
        elif h.get("value"):
            try:
                validate_header_value(h["value"])
                headers[name] = h["value"]
            except ValueError:
                log.warning("webhook.invalid_header_value_skipped", name=name, wh_id=wh_id)

    t0 = time.monotonic()
    http_status: int | None = None
    error: str | None = None
    elapsed: int = 0
    try:
        resp = await _http_post(url, headers=headers, content=payload_bytes)
        http_status = resp.status_code
    except Exception as exc:
        error = str(exc)[:200]
        log.warning("webhook.call_failed", url=url, error=error)
    finally:
        elapsed = int((time.monotonic() - t0) * 1000)

    try:
        await _insert_call(
            config_pool,
            workspace_id=workspace_id,
            webhook_id=wh_id,
            job_id=job_id,
            correlation_id=correlation_id,
            triggered_by=triggered_by,
            webhook_url=url,
            http_status=http_status,
            error=error,
            duration_ms=elapsed,
        )
    except Exception:
        log.exception("webhook.audit_insert_failed", wh_id=wh_id)


async def dispatch_webhooks(
    *,
    config_pool: Any,
    workspace_id: str,
    workspace_name: str,
    job_id: str,
    correlation_id: str,
    triggered_by: str,
    status: str,
    files_changed: int,
    files_skipped: int,
    duration_ms: int | None,
    finished_at: str | None,
    error_message: str | None,
    webhook_secret: str | None,
    resolver: _ResolverProtocol | None,
    git_repo: str | None = None,
    git_branch: str | None = None,
    git_commit: str | None = None,
) -> None:
    """Appelle tous les webhooks actives du workspace en parallele. Fire-and-forget."""
    try:
        webhooks = await fetch_all(
            config_pool,
            "SELECT id, url FROM workspace_webhooks WHERE workspace_id=$1::uuid AND enabled=true",
            workspace_id,
        )
        if not webhooks:
            return

        payload = _build_payload(
            event="indexation.completed",
            workspace=workspace_name,
            triggered_by=triggered_by,
            job_id=job_id,
            status=status,
            files_changed=files_changed,
            files_skipped=files_skipped,
            duration_ms=duration_ms,
            finished_at=finished_at,
            error_message=error_message,
        )
        payload_bytes = json.dumps(payload, default=str).encode("utf-8")

        if webhook_secret is None:
            log.warning("webhook.dispatch_no_secret", workspace=workspace_name)
        signature = _sign_payload(webhook_secret, payload_bytes)

        tasks = []
        for wh in webhooks:
            raw_headers = await fetch_all(
                config_pool,
                "SELECT name, value, vault_ref, enabled FROM webhook_headers WHERE webhook_id=$1",
                wh["id"],
            )
            tasks.append(
                _call_one_webhook(
                    webhook=wh,
                    raw_headers=list(raw_headers),
                    payload_bytes=payload_bytes,
                    correlation_id=correlation_id,
                    triggered_by=triggered_by,
                    git_repo=git_repo,
                    git_branch=git_branch,
                    git_commit=git_commit,
                    signature=signature,
                    config_pool=config_pool,
                    workspace_id=workspace_id,
                    job_id=job_id,
                    resolver=resolver,
                )
            )
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        log.exception("webhook.dispatch_error", workspace=workspace_name)
