from __future__ import annotations

import json
import shutil
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

from rag.indexer.protocol import IndexerProtocol
from rag.schemas.sync import ChangeSet, JobToProcess
from rag.secrets.refs import build_ref, is_vault_ref
from rag.secrets.resolver import VaultLookupFailed
from rag.services.job_log_bus import JobLogBus
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
                SELECT id FROM index_jobs
                WHERE status = 'pending'
                ORDER BY id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE index_jobs j
            SET status='running', started_at=now()
            FROM picked
            WHERE j.id = picked.id
            RETURNING
                j.id AS job_id,
                j.workspace_id,
                j.source_id
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
    )


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


class _ClientProviderProtocol(Protocol):
    async def get_default_vault_name(self) -> str | None: ...


_ERROR_MESSAGE_MAX = 500


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


async def execute_next_pending_job(
    *,
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
    client_provider: _ClientProviderProtocol,
    job_log_bus: JobLogBus | None = None,
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
        default_vault_name = await client_provider.get_default_vault_name()
        await _process_job(
            job=job,
            config_pool=config_pool,
            storage=storage,
            indexer=indexer,
            resolver=resolver,
            default_vault_name=default_vault_name,
            job_log_bus=job_log_bus,
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


async def _process_job(
    *,
    job: JobToProcess,
    config_pool: asyncpg.Pool,
    storage: RepoStorage,
    indexer: IndexerProtocol,
    resolver: _ResolverProtocol,
    default_vault_name: str | None,
    job_log_bus: JobLogBus | None = None,
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

    # 1. Résolution token (lazy). Si auth_ref présent mais pas de coffre
    # par défaut configuré, on échoue le job proprement.
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
    storage.ensure_exists(workspace_id=job.workspace_id, source_id=job.source_id)
    dest = storage.path_for(workspace_id=job.workspace_id, source_id=job.source_id)

    if storage.has_git(workspace_id=job.workspace_id, source_id=job.source_id):
        _log("info", "git pull…")
        await pull(dest=dest, branch=branch)
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
        await clone(url=url, branch=branch, token=token, dest=dest)
        was_fresh_clone = True

    current = await head_commit(dest)
    _log("info", f"HEAD : {current[:12]}")

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

    _log(
        "info",
        f"À traiter : {len(changes.added)} ajoutés, "
        f"{len(changes.modified)} modifiés, {len(changes.deleted)} supprimés.",
    )

    # 4. Traite les fichiers
    files_changed = 0
    files_skipped = 0

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

    for path in changes.deleted:
        await indexer.delete_file(workspace_id=job.workspace_id, path=path)
        files_changed += 1

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
