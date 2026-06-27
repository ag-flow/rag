from __future__ import annotations

import datetime
import json
import shutil
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.db.path_strategies import upsert_strategies_batch
from rag.indexer.protocol import IndexerProtocol
from rag.schemas.sync import ChangeSet, JobToProcess
from rag.secrets.refs import build_ref, is_vault_ref
from rag.secrets.resolver import VaultLookupFailed
from rag.services.circuit_breaker import open_circuit
from rag.services.job_log_bus import JobLogBus
from rag.services.webhook_dispatch import dispatch_webhooks
from rag.sync.error_classifier import classify_indexer_error
from rag.sync.git_ops import (
    GitCloneError,
    GitPullError,
    clone,
    diff_changes,
    filter_glob,
    head_commit,
    list_all_files,
    pull,
    sanitize_git_output,
)
from rag.sync.repo_storage import RepoStorage
from rag.sync.strategy_config import parse_strategy_file

log = structlog.get_logger(__name__)


async def pick_next_pending_job(
    config_pool: asyncpg.Pool,
) -> JobToProcess | None:
    """Picke le job pending le plus ancien et le transitionne en running
    atomiquement (CTE + UPDATE … FROM).

    Retourne `None` si aucun job pending. Sinon retourne un `JobToProcess`
    avec tout le contexte nécessaire à l'executor (workspace, source, indexer).

    `FOR UPDATE SKIP LOCKED` rend l'opération safe pour multi-worker M3+.
    """
    async with config_pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            WITH picked AS (
                SELECT j.id FROM index_jobs j
                WHERE j.status = 'pending'
                  AND (j.retry_after IS NULL OR j.retry_after <= now())
                  AND NOT EXISTS (
                      SELECT 1 FROM indexer_circuit_breakers cb
                      WHERE cb.workspace_id = j.workspace_id
                        AND (cb.open_until IS NULL OR cb.open_until > now())
                  )
                ORDER BY j.id
                LIMIT 1
                FOR UPDATE OF j SKIP LOCKED
            )
            UPDATE index_jobs j
            SET status='running', started_at=now()
            FROM picked
            WHERE j.id = picked.id
            RETURNING
                j.id AS job_id,
                j.workspace_id,
                j.source_id,
                j.triggered_by,
                j.correlation_id,
                j.retry_count
            """
        )
        if row is None:
            return None

        context = await conn.fetchrow(
            """
            SELECT
                w.name AS workspace_name,
                ws.config AS source_config,
                ic.provider AS indexer_provider,
                ic.model AS indexer_model
            FROM workspaces w
            LEFT JOIN workspace_sources ws ON ws.id = $1
            LEFT JOIN indexer_configs ic ON ic.workspace_id = w.id
            WHERE w.id = $2
            """,
            row["source_id"],
            row["workspace_id"],
        )

    if context is None:
        log.error("sync.picker.workspace_not_found", workspace_id=str(row["workspace_id"]))
        return None

    # asyncpg renvoie le jsonb sous forme de str dans ce repo
    raw_cfg = context["source_config"]
    source_config = json.loads(raw_cfg) if isinstance(raw_cfg, str) else dict(raw_cfg or {})

    return JobToProcess(
        job_id=row["job_id"],
        workspace_id=row["workspace_id"],
        workspace_name=context["workspace_name"],
        source_id=row["source_id"],
        source_config=source_config,
        indexer_provider=context["indexer_provider"] or "",
        indexer_model=context["indexer_model"] or "",
        triggered_by=row["triggered_by"],
        correlation_id=str(row["correlation_id"]) if row["correlation_id"] else None,
        retry_count=row["retry_count"],
    )


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


class _ClientProviderProtocol(Protocol):
    async def get_default_vault_name(self) -> str | None: ...


_ERROR_MESSAGE_MAX = 500
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_LIMIT_SECONDS = 4 * 3600  # 4 heures


def _backoff_delay(retry_count: int) -> int:
    """30s * 2^retry_count : 30s, 60s, 120s, 240s ... jusqu'a ~4h."""
    return _BACKOFF_BASE_SECONDS * (2 ** retry_count)


def _should_retry(retry_count: int) -> bool:
    """Retourne False quand le prochain délai dépasserait 4 heures."""
    return _backoff_delay(retry_count) <= _BACKOFF_LIMIT_SECONDS


def _truncate(s: str, n: int = _ERROR_MESSAGE_MAX) -> str:
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def _to_vault_ref(logical_key: str, vault_name: str) -> str:
    """Construit une ref ``${vault://<vault_name>:<logical>}`` dynamique."""
    return build_ref(vault_name, logical_key)


async def _resolve_token(
    resolver: _ResolverProtocol,
    config: dict[str, Any],
    default_vault_name: str,
) -> str | None:
    """Résout `auth_ref` si présent. None si source publique."""
    auth_ref = config.get("auth_ref")
    if not auth_ref:
        return None
    if is_vault_ref(auth_ref):
        return await resolver.resolve_with_retry(auth_ref)
    return await resolver.resolve_with_retry(_to_vault_ref(auth_ref, default_vault_name))


def _format_error(e: BaseException) -> str:
    """Format compact pour `index_jobs.error_message`, sanitized."""
    if isinstance(e, GitCloneError):
        return _truncate(f"git clone failed: {sanitize_git_output(str(e))}")
    if isinstance(e, GitPullError):
        return _truncate(f"git pull failed: {sanitize_git_output(str(e))}")
    if isinstance(e, VaultLookupFailed):
        return _truncate(f"auth_ref not resolvable: {e}")
    return _truncate(
        f"unexpected: {type(e).__name__}: {sanitize_git_output(str(e))}",
        200,
    )


async def _mark_job_error(
    config_pool: asyncpg.Pool,
    *,
    job_id: UUID,
    error_message: str,
) -> None:
    async with config_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE index_jobs
            SET status='error',
                error_message=$1,
                finished_at=now(),
                duration_ms=CASE
                    WHEN started_at IS NOT NULL THEN
                        EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                    ELSE 0
                END
            WHERE id=$2
            """,
            error_message,
            job_id,
        )


async def _reschedule_job(
    config_pool: asyncpg.Pool,
    *,
    job_id: UUID,
    retry_count: int,
    delay_seconds: int,
) -> None:
    retry_after = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        seconds=delay_seconds
    )
    await config_pool.execute(
        """
        UPDATE index_jobs
        SET status='pending',
            retry_count=$1,
            retry_after=$2,
            started_at=NULL
        WHERE id=$3
        """,
        retry_count,
        retry_after,
        job_id,
    )


async def _execute_push_job(
    *,
    job: JobToProcess,
    config_pool: asyncpg.Pool,
    indexer: IndexerProtocol,
    webhook_secret: str | None,
    resolver: _ResolverProtocol | None,
    client_provider: _ClientProviderProtocol,
) -> None:
    jid = str(job.job_id)
    final_status = "error"
    files_changed = 0
    files_skipped = 0
    error_message: str | None = None
    duration_ms: int | None = None
    enrichment_results: list[dict] = []

    try:
        row = await config_pool.fetchrow(
            "SELECT path, content, title, strategy_override FROM push_job_payloads WHERE job_id=$1",
            job.job_id,
        )
        if row is None:
            raise RuntimeError(f"push_job_payloads not found for job {jid}")

        path, content = row["path"], row["content"]
        title = row["title"]
        strategy_override = row["strategy_override"]
        content_hash = "sha256:" + sha256(content.encode("utf-8")).hexdigest()

        existing = await config_pool.fetchval(
            "SELECT content_hash FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
            job.workspace_id,
            path,
        )

        if existing == content_hash:
            await config_pool.execute(
                """
                UPDATE index_jobs
                SET status='skipped', finished_at=now(),
                    duration_ms=CASE
                        WHEN started_at IS NOT NULL THEN
                            EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                        ELSE 0
                    END
                WHERE id=$1
                """,
                job.job_id,
            )
            final_status = "skipped"
            files_skipped = 1
        else:
            await indexer.index_file(
                workspace_id=job.workspace_id,
                path=path,
                content=content,
                content_hash=content_hash,
                indexer_used=job.indexer_used,
                title=title,
                strategy_override=strategy_override,
            )

            # Enrichissements LLM post-indexation
            try:
                from rag.services.enrichments import run_enrichments
                async with config_pool.acquire() as _enrich_conn:
                    _enrichments = await run_enrichments(
                        conn=_enrich_conn,
                        indexer=indexer,
                        workspace_id=str(job.workspace_id),
                        workspace_name=job.workspace_name,
                        path=path,
                        content=content,
                        content_hash=content_hash,
                        vault_svc=client_provider,
                        client_provider=client_provider,
                        config_pool=config_pool,
                    )
                    enrichment_results.extend(_enrichments)
            except Exception as _exc:
                log.warning("sync.executor.enrichment_failed", path=path, error=str(_exc))

            await config_pool.execute(
                """
                UPDATE index_jobs
                SET status='done', finished_at=now(), files_changed=1,
                    duration_ms=CASE
                        WHEN started_at IS NOT NULL THEN
                            EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                        ELSE 0
                    END
                WHERE id=$1
                """,
                job.job_id,
            )
            final_status = "done"
            files_changed = 1

        log.info(
            "push_job.done",
            job_id=jid,
            workspace=job.workspace_name,
            status=final_status,
        )
    except Exception as e:
        error_message = _truncate(str(e))
        family = classify_indexer_error(e)
        if family == "transient" and _should_retry(job.retry_count):
            delay = _backoff_delay(job.retry_count)
            await _reschedule_job(
                config_pool,
                job_id=job.job_id,
                retry_count=job.retry_count + 1,
                delay_seconds=delay,
            )
            final_status = "retrying"
            log.warning(
                "push_job.transient_error_retry",
                job_id=jid,
                retry_count=job.retry_count + 1,
                delay_seconds=delay,
                error=error_message,
            )
        else:
            await _mark_job_error(
                config_pool, job_id=job.job_id, error_message=error_message
            )
            final_status = "error"
            if family in ("blocking", "transient"):
                # transient ici = retries épuisés → même traitement que blocking
                await open_circuit(
                    config_pool,
                    workspace_id=job.workspace_id,
                    provider=job.indexer_provider,
                    model=job.indexer_model,
                    error_message=error_message,
                )
            log.exception("push_job.error", job_id=jid, family=family)
    finally:
        if final_status != "retrying":
            try:
                await config_pool.execute(
                    "DELETE FROM push_job_payloads WHERE job_id=$1", job.job_id
                )
            except Exception:
                log.warning("push_job.payload_cleanup_failed", job_id=jid)

    if final_status == "retrying":
        return

    finished_at = datetime.datetime.now(datetime.UTC).isoformat()
    correlation_id = job.correlation_id or jid
    await dispatch_webhooks(
        config_pool=config_pool,
        workspace_id=str(job.workspace_id),
        workspace_name=job.workspace_name,
        job_id=jid,
        correlation_id=correlation_id,
        triggered_by=job.triggered_by,
        status=final_status,
        files_changed=files_changed,
        files_skipped=files_skipped,
        duration_ms=duration_ms,
        finished_at=finished_at,
        error_message=error_message,
        webhook_secret=webhook_secret,
        resolver=resolver,
        enrichments=enrichment_results,
    )


async def _execute_delete_job(
    *,
    job: JobToProcess,
    config_pool: asyncpg.Pool,
    indexer: IndexerProtocol,
    webhook_secret: str | None,
    resolver: _ResolverProtocol | None,
) -> None:
    jid = str(job.job_id)
    final_status = "error"
    files_changed = 0
    files_skipped = 0
    error_message: str | None = None
    duration_ms: int | None = None

    try:
        row = await config_pool.fetchrow(
            "SELECT path FROM delete_job_payloads WHERE job_id=$1",
            job.job_id,
        )
        if row is None:
            raise RuntimeError(f"delete_job_payloads not found for job {jid}")

        path = row["path"]

        exists = await config_pool.fetchval(
            "SELECT 1 FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
            job.workspace_id,
            path,
        )

        if not exists:
            await config_pool.execute(
                """
                UPDATE index_jobs
                SET status='skipped', finished_at=now(),
                    duration_ms=CASE
                        WHEN started_at IS NOT NULL THEN
                            EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                        ELSE 0
                    END
                WHERE id=$1
                """,
                job.job_id,
            )
            final_status = "skipped"
            files_skipped = 1
        else:
            await indexer.delete_file(workspace_id=job.workspace_id, path=path)
            await config_pool.execute(
                """
                UPDATE index_jobs
                SET status='done', finished_at=now(), files_changed=1,
                    duration_ms=CASE
                        WHEN started_at IS NOT NULL THEN
                            EXTRACT(MILLISECONDS FROM (now() - started_at))::int
                        ELSE 0
                    END
                WHERE id=$1
                """,
                job.job_id,
            )
            final_status = "done"
            files_changed = 1

        log.info(
            "delete_job.done",
            job_id=jid,
            workspace=job.workspace_name,
            status=final_status,
        )
    except Exception as e:
        error_message = _truncate(str(e))
        family = classify_indexer_error(e)
        if family == "transient" and _should_retry(job.retry_count):
            delay = _backoff_delay(job.retry_count)
            await _reschedule_job(
                config_pool,
                job_id=job.job_id,
                retry_count=job.retry_count + 1,
                delay_seconds=delay,
            )
            final_status = "retrying"
            log.warning(
                "delete_job.transient_error_retry",
                job_id=jid,
                retry_count=job.retry_count + 1,
                delay_seconds=delay,
                error=error_message,
            )
        else:
            await _mark_job_error(
                config_pool, job_id=job.job_id, error_message=error_message
            )
            final_status = "error"
            if family in ("blocking", "transient"):
                await open_circuit(
                    config_pool,
                    workspace_id=job.workspace_id,
                    provider=job.indexer_provider,
                    model=job.indexer_model,
                    error_message=error_message,
                )
            log.exception("delete_job.error", job_id=jid, family=family)
    finally:
        if final_status != "retrying":
            try:
                await config_pool.execute(
                    "DELETE FROM delete_job_payloads WHERE job_id=$1", job.job_id
                )
            except Exception:
                log.warning("delete_job.payload_cleanup_failed", job_id=jid)

    if final_status == "retrying":
        return

    finished_at = datetime.datetime.now(datetime.UTC).isoformat()
    correlation_id = job.correlation_id or jid
    await dispatch_webhooks(
        config_pool=config_pool,
        workspace_id=str(job.workspace_id),
        workspace_name=job.workspace_name,
        job_id=jid,
        correlation_id=correlation_id,
        triggered_by=job.triggered_by,
        status=final_status,
        files_changed=files_changed,
        files_skipped=files_skipped,
        duration_ms=duration_ms,
        finished_at=finished_at,
        error_message=error_message,
        webhook_secret=webhook_secret,
        resolver=resolver,
        enrichments=[],
    )


async def execute_next_pending_job(
    *,
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
    client_provider: _ClientProviderProtocol,
    job_log_bus: JobLogBus | None = None,
    webhook_secret: str | None = None,
) -> bool:
    """Picke 1 job pending + exécute le pipeline complet.

    Retourne True si un job a été traité (peu importe done/error), False si
    aucun job pending.

    Si la source nécessite un secret (`auth_ref` présent) mais qu'aucun coffre
    Harpocrate par défaut n'est configuré, le job est marqué en erreur (le
    worker ne plante pas, le tick suivant rejouera).
    """
    job = await pick_next_pending_job(config_pool)
    if job is None:
        return False

    try:
        if job.triggered_by == "push":
            await _execute_push_job(
                job=job,
                config_pool=config_pool,
                indexer=indexer,
                webhook_secret=webhook_secret,
                resolver=resolver,
                client_provider=client_provider,
            )
        elif job.triggered_by == "delete":
            await _execute_delete_job(
                job=job,
                config_pool=config_pool,
                indexer=indexer,
                webhook_secret=webhook_secret,
                resolver=resolver,
            )
        else:
            default_vault_name = await client_provider.get_default_vault_name()
            await _execute_git_job(
                job=job,
                config_pool=config_pool,
                storage=storage,
                indexer=indexer,
                resolver=resolver,
                default_vault_name=default_vault_name,
                client_provider=client_provider,
                job_log_bus=job_log_bus,
                webhook_secret=webhook_secret,
            )
    except Exception as e:
        msg = _format_error(e)
        log.exception("sync.executor.job_error", job_id=str(job.job_id))
        await _mark_job_error(config_pool, job_id=job.job_id, error_message=msg)
        if job_log_bus is not None:
            jid = str(job.job_id)
            job_log_bus.publish(jid, "error", f"Erreur : {msg}")
            job_log_bus.complete(jid, status="error")
    return True


async def _execute_git_job(
    *,
    job: JobToProcess,
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
    default_vault_name: str | None,
    client_provider: _ClientProviderProtocol,
    job_log_bus: JobLogBus | None = None,
    webhook_secret: str | None,
) -> None:
    jid = str(job.job_id)
    bus = job_log_bus

    def _log(level: str, msg: str) -> None:
        if bus is not None:
            bus.publish(jid, level, msg)

    config = job.source_config
    url = config["url"]
    branch = config.get("branch", "main")
    include = config.get("include") or ["**/*"]
    exclude = config.get("exclude") or []
    last_commit = config.get("last_commit")

    _log("info", f"Démarrage — source : {url} (branche {branch})")

    # 1. Résolution auth (lazy). Deux cas : SSH ou token/public.
    auth_type = config.get("auth_type", "token")
    token: str | None = None
    ssh_key: str | None = None
    ssh_username: str | None = config.get("ssh_username") or "git"

    if auth_type == "ssh":
        ssh_key_ref = config.get("ssh_key_ref")
        if ssh_key_ref:
            if is_vault_ref(ssh_key_ref):
                ssh_key = await resolver.resolve_with_retry(ssh_key_ref)
            else:
                if default_vault_name is None:
                    raise RuntimeError("no default Harpocrate vault configured")
                ssh_key = await resolver.resolve_with_retry(
                    _to_vault_ref(ssh_key_ref, default_vault_name)
                )
            _log("info", "Auth : clé SSH résolue.")
        else:
            _log("info", "Auth : source publique (SSH sans clé).")
    else:
        if config.get("auth_ref") and default_vault_name is None:
            raise RuntimeError("no default Harpocrate vault configured")
        token = (
            await _resolve_token(resolver, config, default_vault_name)
            if default_vault_name is not None
            else None
        )
        if token:
            _log("info", "Auth : token résolu.")
        else:
            _log("info", "Auth : source publique.")

    # 2. Path local + clone ou pull
    # source_id est toujours non-None pour les jobs git.
    if job.source_id is None:
        raise RuntimeError(f"git job {job.job_id} sans source_id")
    storage.ensure_exists(workspace_id=job.workspace_id, source_id=job.source_id)
    dest = storage.path_for(workspace_id=job.workspace_id, source_id=job.source_id)

    if storage.has_git(workspace_id=job.workspace_id, source_id=job.source_id):
        _log("info", "git pull…")
        await pull(dest=dest, branch=branch, ssh_key=ssh_key)
        was_fresh_clone = False
    else:
        # Le ensure_exists a créé un dossier vide. `git clone` exige que la
        # cible n'existe pas (ou soit vide). On vide puis on retire.
        if dest.exists():
            for child in dest.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            dest.rmdir()
        _log("info", f"git clone {url}…")
        await clone(
                    url=url,
                    branch=branch,
                    token=token,
                    dest=dest,
                    ssh_key=ssh_key,
                    ssh_username=ssh_username,
                )
        was_fresh_clone = True

    current = await head_commit(dest)
    _log("info", f"HEAD : {current[:12]}")

    # Mise à jour du correlation_id avec le hash de commit
    await config_pool.execute(
        "UPDATE index_jobs SET correlation_id=$1 WHERE id=$2", current, job.job_id
    )

    # 3. Diff
    # Si pas de last_commit, ou clone frais, ou HEAD identique : on bascule
    # sur la liste exhaustive pour passer chaque fichier dans le filtre dedup
    # (qui les classera en skipped si le hash est inchangé).
    if last_commit is None or was_fresh_clone or last_commit == current:
        all_files = await list_all_files(dest)
        changes = ChangeSet(added=all_files)
    else:
        changes = await diff_changes(
            dest=dest,
            from_commit=last_commit,
            to_commit=current,
        )
    changes = filter_glob(changes, include=include, exclude=exclude)

    # Lit .rag/strategy.yml et UPSERT les stratégies en base (le fichier prime sur l'IHM)
    file_strategies = parse_strategy_file(dest)
    if file_strategies:
        await upsert_strategies_batch(config_pool, job.workspace_id, file_strategies)
        _log("info", f"Stratégies depuis .rag/strategy.yml : {len(file_strategies)} path(s).")

    _log(
        "info",
        f"À traiter : {len(changes.added)} ajoutés, "
        f"{len(changes.modified)} modifiés, {len(changes.deleted)} supprimés.",
    )

    # 4. Traite les fichiers
    files_changed = 0
    files_skipped = 0
    changed_files: list[tuple[str, str]] = []  # (path, change_type)
    added_set = set(changes.added)
    enrichment_results: list[dict] = []

    for path in changes.added + changes.modified:
        full = dest / path
        try:
            content = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue  # binaire / lien cassé → skip silencieux

        content_hash = "sha256:" + sha256(content.encode("utf-8")).hexdigest()

        async with config_pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT content_hash FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
                job.workspace_id,
                path,
            )
        if existing == content_hash:
            files_skipped += 1
            continue

        await indexer.index_file(
            workspace_id=job.workspace_id,
            path=path,
            content=content,
            content_hash=content_hash,
            indexer_used=job.indexer_used,
        )
        files_changed += 1
        changed_files.append((path, "added" if path in added_set else "modified"))

        # Enrichissements LLM post-indexation
        try:
            from rag.services.enrichments import run_enrichments
            async with config_pool.acquire() as _enrich_conn:
                _enrichments = await run_enrichments(
                    conn=_enrich_conn,
                    indexer=indexer,
                    workspace_id=str(job.workspace_id),
                    workspace_name=job.workspace_name,
                    path=path,
                    content=content,
                    content_hash=content_hash,
                    vault_svc=client_provider,
                    client_provider=client_provider,
                    config_pool=config_pool,
                )
                enrichment_results.extend(_enrichments)
        except Exception as _exc:
            log.warning("sync.executor.enrichment_failed", path=path, error=str(_exc))

    for path in changes.deleted:
        await indexer.delete_file(workspace_id=job.workspace_id, path=path)
        files_changed += 1
        changed_files.append((path, "deleted"))

    # 5. Update workspace_sources : last_commit + last_indexed_at
    async with config_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE workspace_sources
            SET config = jsonb_set(
                    coalesce(config, '{}'::jsonb),
                    '{last_commit}',
                    to_jsonb($1::text)
                ),
                last_indexed_at = now()
            WHERE id = $2
            """,
            current,
            job.source_id,
        )

    # 6. Mark done
    async with config_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE index_jobs
            SET status='done',
                finished_at=now(),
                duration_ms=EXTRACT(MILLISECONDS FROM (now() - started_at))::int,
                files_changed=$1,
                files_skipped=$2
            WHERE id=$3
            """,
            files_changed,
            files_skipped,
            job.job_id,
        )
        if changed_files:
            try:
                await conn.execute(
                    """
                    INSERT INTO index_job_files (job_id, path, change_type)
                    SELECT $1, p, t FROM unnest($2::text[], $3::text[]) AS u(p, t)
                    """,
                    job.job_id,
                    [p for p, _ in changed_files],
                    [t for _, t in changed_files],
                )
            except Exception:
                log.warning("sync.executor.job_files_persist_failed", job_id=jid)

    log.info(
        "sync.executor.job_done",
        job_id=jid,
        workspace=job.workspace_name,
        files_changed=files_changed,
        files_skipped=files_skipped,
    )
    _log("info", f"Terminé : {files_changed} fichiers mis à jour, {files_skipped} ignorés.")
    if bus is not None:
        bus.complete(jid, status="done", files_changed=files_changed, files_skipped=files_skipped)

    # 7. Dispatch webhooks
    finished_at_str = datetime.datetime.now(datetime.UTC).isoformat()
    correlation_id_val = current  # the commit hash
    await dispatch_webhooks(
        config_pool=config_pool,
        workspace_id=str(job.workspace_id),
        workspace_name=job.workspace_name,
        job_id=jid,
        correlation_id=correlation_id_val,
        triggered_by=job.triggered_by,
        status="done",
        files_changed=files_changed,
        files_skipped=files_skipped,
        duration_ms=None,
        finished_at=finished_at_str,
        error_message=None,
        webhook_secret=webhook_secret,
        resolver=resolver,
        git_repo=url,
        git_branch=branch,
        git_commit=current,
        enrichments=enrichment_results,
    )
