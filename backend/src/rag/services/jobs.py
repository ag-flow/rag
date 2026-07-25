from __future__ import annotations

import json
from typing import Any, Literal, Protocol

import asyncpg
import structlog

from rag.api.errors import (
    ChunkingChangeRequiresReindex,
    IndexerChangeRequiresReindex,
    JobNotFound,
    RefNotFoundInVault,
    SourceNotFound,
    VaultUnreachable,
    WorkspaceNotFound,
)
from rag.db.helpers import fetch_all, fetch_one
from rag.db.workspace_schema import (
    derive_workspace_dsn,
    provision_workspace_schema,
    reset_workspace_schema,
)
from rag.schemas.admin import ChunkingConfigSpec, IndexerSpec
from rag.secrets.refs import build_ref
from rag.secrets.resolver import VaultLookupFailed
from rag.services.chunking_configs import get_chunking_config, upsert_chunking_config
from rag.services.models import get_dimension_or_raise

log = structlog.get_logger(__name__)

ApplyChunkingResult = (
    Literal["no_change"]
    | tuple[Literal["updated"], dict[str, Any]]
    | tuple[Literal["reindex_triggered"], dict[str, Any]]
)


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


async def create_source_pending_job(
    *, workspace_name: str, source_id: str, config_pool: asyncpg.Pool
) -> dict[str, Any]:
    """Insère un job en status 'pending' pour une source spécifique.

    Lève WorkspaceNotFound si le workspace n'existe pas.
    Lève SourceNotFound si la source n'appartient pas au workspace.
    """
    row = await fetch_one(
        config_pool,
        """
        INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status)
        SELECT w.id, $2::uuid, 'manual', 'pending'
        FROM workspaces w
        JOIN workspace_sources ws ON ws.id = $2::uuid AND ws.workspace_id = w.id
        WHERE w.name = $1
        RETURNING id, triggered_by, status, files_changed, files_skipped,
                  error_message, started_at, finished_at, duration_ms
        """,
        workspace_name,
        source_id,
    )
    if row is None:
        ws = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name=$1", workspace_name)
        if ws is None:
            raise WorkspaceNotFound(workspace_name)
        raise SourceNotFound(source_id)

    log.info("job.created_pending_source", workspace=workspace_name, source_id=source_id)
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
        SELECT id, triggered_by, source_id, path, params, status, files_changed, files_skipped,
               error_message, started_at, finished_at, duration_ms
        FROM index_jobs
        WHERE workspace_id = $1
        ORDER BY started_at DESC NULLS LAST, id DESC
        """,
        ws["id"],
    )
    return [_job_to_dict(r) for r in rows]


async def list_jobs_global(
    config_pool: asyncpg.Pool,
    *,
    limit: int = 50,
    workspace: str | None = None,
    status: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Liste globale cross-workspace des jobs, plus récents en premier (created_at DESC).

    Jointure sur `workspaces` pour exposer `workspace_name`. Filtres optionnels
    par nom de workspace, par status et par `source` (rest_api / webhook / git /
    admin — dérivée de triggered_by + source_id) ; `limit` borné par le caller.
    """
    rows = await fetch_all(
        config_pool,
        """
        SELECT u.id, u.triggered_by, u.source_id, u.path, u.params, u.status,
               u.files_changed, u.files_skipped, u.error_message,
               u.started_at, u.finished_at, u.duration_ms, u.workspace_name
        FROM (
            SELECT j.id::text AS id, j.triggered_by, j.source_id, j.path, j.params, j.status,
                   j.files_changed, j.files_skipped, j.error_message,
                   j.started_at, j.finished_at, j.duration_ms,
                   w.name AS workspace_name, j.created_at AS sort_ts
            FROM index_jobs j
            JOIN workspaces w ON w.id = j.workspace_id
            UNION ALL
            -- Demandes d'ingestion REJETÉES (aucun job) : affichées comme des
            -- lignes de statut 'rejected', source rest_api, motif en error_message.
            SELECT r.id::text,
                   CASE WHEN r.method = 'DELETE' THEN 'delete' ELSE 'push' END,
                   NULL::uuid, r.doc_path, NULL::jsonb, 'rejected',
                   0, 0, r.reason,
                   r.received_at, NULL::timestamptz, NULL::int,
                   r.workspace, r.received_at
            FROM ingestion_rejections r
        ) u
        WHERE ($1::text IS NULL OR u.workspace_name = $1)
          AND ($2::text IS NULL OR u.status = $2)
          AND ($4::text IS NULL OR (
              ($4 = 'rest_api' AND u.triggered_by IN ('push', 'reindex_document', 'delete'))
              OR ($4 = 'webhook' AND u.triggered_by = 'webhook')
              OR ($4 = 'git' AND u.source_id IS NOT NULL AND u.triggered_by <> 'webhook')
              OR ($4 = 'admin' AND u.source_id IS NULL
                  AND u.triggered_by IN ('manual', 'reindex_indexer_change',
                                         'reindex_chunking_change', 'rebuild_lexical_index'))
          ))
        ORDER BY u.sort_ts DESC, u.id DESC
        LIMIT $3
        """,
        workspace,
        status,
        limit,
        source,
    )
    return [{**_job_to_dict(r), "workspace_name": r["workspace_name"]} for r in rows]


async def get_job(
    config_pool: asyncpg.Pool, *, workspace_name: str, job_id: str
) -> dict[str, Any]:
    """Statut d'un job unique, scopé au workspace. Lève JobNotFound si absent/étranger."""
    row = await fetch_one(
        config_pool,
        """
        SELECT j.id, j.triggered_by, j.source_id, j.path, j.params, j.status,
               j.files_changed, j.files_skipped, j.error_message,
               j.started_at, j.finished_at, j.duration_ms
        FROM index_jobs j
        JOIN workspaces w ON w.id = j.workspace_id
        WHERE j.id = $1::uuid AND w.name = $2
        """,
        job_id,
        workspace_name,
    )
    if row is None:
        raise JobNotFound(job_id)
    return _job_to_dict(row)


async def list_job_files(
    config_pool: asyncpg.Pool, *, workspace_name: str, job_id: str, limit: int = 1000
) -> dict[str, Any]:
    """Fichiers traités par un job (added/modified/deleted), limités à `limit`.

    Lève JobNotFound si le job n'appartient pas au workspace.
    """
    owner = await fetch_one(
        config_pool,
        """
        SELECT j.id FROM index_jobs j
        JOIN workspaces w ON w.id = j.workspace_id
        WHERE j.id = $1::uuid AND w.name = $2
        """,
        job_id,
        workspace_name,
    )
    if owner is None:
        raise JobNotFound(job_id)

    files = await fetch_all(
        config_pool,
        """
        SELECT path, change_type FROM index_job_files
        WHERE job_id = $1::uuid
        ORDER BY change_type, path
        LIMIT $2
        """,
        job_id,
        limit,
    )
    total = await fetch_one(
        config_pool,
        "SELECT count(*) AS n FROM index_job_files WHERE job_id = $1::uuid",
        job_id,
    )
    return {
        "files": [{"path": r["path"], "change_type": r["change_type"]} for r in files],
        "total": int(total["n"]),
        "limit": limit,
    }


# Déclencheurs de reconfig admin (source_id NULL, non liés à une source git/API).
_ADMIN_TRIGGERS = frozenset(
    {"manual", "reindex_indexer_change", "reindex_chunking_change", "rebuild_lexical_index"}
)
_REST_TRIGGERS = frozenset({"push", "reindex_document", "delete"})


def _job_source(triggered_by: str, source_id: Any) -> str:
    """Origine du job, dérivée du déclencheur + de la présence d'une source git.

    - rest_api : indexation par clé API (push / ré-évaluation / suppression) ;
    - webhook  : notification git entrante ;
    - git      : synchronisation d'une source git (planifiée ou manuelle) ;
    - admin    : reconfiguration déclenchée depuis l'IHM (changement d'indexeur…).
    """
    if triggered_by in _REST_TRIGGERS:
        return "rest_api"
    if triggered_by == "webhook":
        return "webhook"
    if source_id is not None:
        return "git"
    return "admin"


def _job_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "triggered_by": row["triggered_by"],
        "source": _job_source(row["triggered_by"], row.get("source_id")),
        "path": row.get("path"),
        "params": json.loads(row["params"]) if row.get("params") else None,
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

    # `api_key_ref=None` signifie « champ omis » côté client, pas « retirer
    # la ref » : on le traite comme inchangé (sémantique COALESCE) pour ne
    # pas déclencher le drop/recreate destructif ni nuller la ref stockée
    # (BUG-062).
    effective_api_key_ref: str | None = None
    if new_indexer is not None:
        effective_api_key_ref = new_indexer.api_key_ref or row["api_key_ref"]

    same_indexer = new_indexer is None or (
        new_indexer.provider == row["provider"]
        and new_indexer.model == row["model"]
        and (effective_api_key_ref or None) == (row["api_key_ref"] or None)
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

    # Reprovisionne intégralement le schéma workspace avec la nouvelle dimension.
    # On réinitialise le schéma (drop embeddings + sections + historique de
    # migrations) puis on rejoue create_embeddings_table + toutes les migrations
    # workspace via la fonction de provisioning partagée avec create_workspace.
    # Sans ce reset, apply_pending resterait un no-op et le schéma serait
    # définitivement divergent (BUG-049).
    ws_dsn = derive_workspace_dsn(admin_dsn, row["rag_base"])
    await reset_workspace_schema(ws_dsn)
    await provision_workspace_schema(ws_dsn, dimension=new_dimension)

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
            effective_api_key_ref,
            new_dimension,
            row["workspace_id"],
        )

    return await create_pending_job(
        workspace_name=name,
        triggered_by="reindex_indexer_change",
        config_pool=config_pool,
    )


def _format_chunking_desc(cfg: dict[str, Any]) -> str:
    """Représentation humaine d'une chunking_config pour le payload 409."""
    return (
        f"{cfg['strategy']} "
        f"(max={cfg['max_chars']}, min={cfg['min_chars']}, "
        f"overlap={cfg['overlap_chars']})"
    )


def _payload_matches_current(payload: ChunkingConfigSpec, current: dict[str, Any]) -> bool:
    """True si les 5 champs comparés du DTO matchent la row existante."""
    return bool(
        payload.strategy == current["strategy"]
        and payload.max_chars == current["max_chars"]
        and payload.min_chars == current["min_chars"]
        and payload.overlap_chars == current["overlap_chars"]
        and payload.extras == current["extras"]
    )


async def apply_chunking_change(
    *,
    name: str,
    payload: ChunkingConfigSpec,
    confirm: bool,
    config_pool: asyncpg.Pool,
) -> ApplyChunkingResult:
    """Applique un changement de chunking_config sur un workspace (M9 §4.6/§5.2).

    - Si ``payload`` est identique à la config actuelle → ``"no_change"``
      (caller renvoie 204).
    - Sinon, compte ``indexed_documents`` du workspace :
        * 0 doc → upsert immédiat + ``("updated", new_cfg)`` (caller 200).
        * >0 doc + ``confirm=False`` → lève
          :class:`ChunkingChangeRequiresReindex` (caller 409).
        * >0 doc + ``confirm=True`` → upsert + ``create_pending_job`` en une
          transaction unique + ``("reindex_triggered", job_row)`` (caller 202).

    Lève :class:`WorkspaceNotFound` si le workspace n'existe pas.

    Note implémentation : la branche reindex utilise un INSERT inline plutôt que
    de ré-appeler :func:`upsert_chunking_config`, parce que le service prend un
    *pool* (pas une connexion). Pour garder l'upsert + l'INSERT du job dans la
    *même* transaction (atomicité requise par le contrat), on duplique le SQL
    de l'upsert. La duplication reste alignée avec
    ``upsert_chunking_config`` — toute évolution du schéma doit être propagée
    aux deux endroits.
    """
    ws_row = await fetch_one(
        config_pool,
        "SELECT id FROM workspaces WHERE name = $1",
        name,
    )
    if ws_row is None:
        raise WorkspaceNotFound(name)
    workspace_id = ws_row["id"]

    current = await get_chunking_config(workspace_id, config_pool)
    if _payload_matches_current(payload, current):
        return "no_change"

    docs = await config_pool.fetchval(
        "SELECT COUNT(*) FROM indexed_documents WHERE workspace_id = $1",
        workspace_id,
    )
    docs_count = int(docs or 0)

    if docs_count == 0:
        # Pas de docs indexés : upsert sans reindex.
        new_cfg = await upsert_chunking_config(
            workspace_id=workspace_id,
            spec=payload,
            config_pool=config_pool,
        )
        log.info(
            "chunking.change_applied",
            workspace=name,
            mode="no_reindex",
        )
        return ("updated", new_cfg)

    if not confirm:
        new_desc_dict: dict[str, Any] = {
            "strategy": payload.strategy,
            "max_chars": payload.max_chars,
            "min_chars": payload.min_chars,
            "overlap_chars": payload.overlap_chars,
        }
        raise ChunkingChangeRequiresReindex(
            workspace=name,
            current=_format_chunking_desc(current),
            new=_format_chunking_desc(new_desc_dict),
        )

    # docs > 0 et confirm=True : upsert + INSERT du job en une transaction.
    async with config_pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """
            INSERT INTO chunking_configs
                (workspace_id, strategy, max_chars, min_chars, overlap_chars, extras)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (workspace_id) DO UPDATE
                SET strategy      = EXCLUDED.strategy,
                    max_chars     = EXCLUDED.max_chars,
                    min_chars     = EXCLUDED.min_chars,
                    overlap_chars = EXCLUDED.overlap_chars,
                    extras        = EXCLUDED.extras,
                    updated_at    = now()
            """,
            workspace_id,
            payload.strategy,
            payload.max_chars,
            payload.min_chars,
            payload.overlap_chars,
            json.dumps(payload.extras),
        )
        job_row = await conn.fetchrow(
            """
            INSERT INTO index_jobs (workspace_id, triggered_by, status)
            VALUES ($1, 'reindex_chunking_change', 'pending')
            RETURNING id, triggered_by, status, files_changed, files_skipped,
                      error_message, started_at, finished_at, duration_ms
            """,
            workspace_id,
        )

    if job_row is None:
        raise RuntimeError("apply_chunking_change: INSERT did not RETURN")

    log.info(
        "chunking.change_applied",
        workspace=name,
        mode="reindex_triggered",
        job_id=str(job_row["id"]),
    )
    return ("reindex_triggered", _job_to_dict(job_row))


_VALID_ENGINES = ("legacy", "structured")


async def apply_engine_change(
    *,
    name: str,
    engine: str,
    confirm: bool,
    config_pool: asyncpg.Pool,
) -> tuple[str, dict[str, Any]] | str:
    """Bascule le moteur de chunking d'un workspace (`legacy` ↔ `structured`).

    Le texte embeddé diffère entre moteurs → tout document indexé doit être
    re-chunké. On invalide donc `indexed_documents` (force le re-chunk au pull
    suivant — pas de drop de table : l'upsert structuré purge les lignes legacy
    par path) puis on enquêue un job `reindex_chunking_change`.

    - identique → ``"no_change"``.
    - 0 doc → bascule immédiate → ``("updated", {...})``.
    - >0 doc + ``confirm=False`` → lève :class:`ChunkingChangeRequiresReindex`.
    - >0 doc + ``confirm=True`` → bascule + invalidation + job en une
      transaction → ``("reindex_triggered", job_dict)``.
    """
    if engine not in _VALID_ENGINES:
        raise ValueError(f"invalid engine {engine!r}, expected one of {_VALID_ENGINES}")

    ws_row = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name = $1", name)
    if ws_row is None:
        raise WorkspaceNotFound(name)
    workspace_id = ws_row["id"]

    current_engine = await config_pool.fetchval(
        "SELECT engine FROM chunking_configs WHERE workspace_id = $1", workspace_id
    )
    if current_engine == engine:
        return "no_change"

    docs = await config_pool.fetchval(
        "SELECT COUNT(*) FROM indexed_documents WHERE workspace_id = $1", workspace_id
    )
    if int(docs or 0) == 0:
        await config_pool.execute(
            "UPDATE chunking_configs SET engine=$1, updated_at=now() WHERE workspace_id=$2",
            engine,
            workspace_id,
        )
        log.info("chunking.engine_changed", workspace=name, engine=engine, mode="no_reindex")
        return ("updated", {"workspace_id": str(workspace_id), "engine": engine})

    if not confirm:
        raise ChunkingChangeRequiresReindex(
            workspace=name,
            current=f"engine={current_engine}",
            new=f"engine={engine}",
        )

    async with config_pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE chunking_configs SET engine=$1, updated_at=now() WHERE workspace_id=$2",
            engine,
            workspace_id,
        )
        await conn.execute(
            "DELETE FROM indexed_documents WHERE workspace_id=$1", workspace_id
        )
        job_row = await conn.fetchrow(
            """
            INSERT INTO index_jobs (workspace_id, triggered_by, status)
            VALUES ($1, 'reindex_chunking_change', 'pending')
            RETURNING id, triggered_by, status, files_changed, files_skipped,
                      error_message, started_at, finished_at, duration_ms
            """,
            workspace_id,
        )
    if job_row is None:
        raise RuntimeError("apply_engine_change: INSERT did not RETURN")

    log.info(
        "chunking.engine_changed",
        workspace=name,
        engine=engine,
        mode="reindex_triggered",
        job_id=str(job_row["id"]),
    )
    return ("reindex_triggered", _job_to_dict(job_row))
class UnknownDefaultStrategyError(ValueError):
    """Stratégie invisible pour ce caller (ni système ni la sienne)."""


async def apply_default_strategy_change(
    *,
    name: str,
    strategy_id: Any,
    owner_id: str,
    confirm: bool,
    config_pool: asyncpg.Pool,
) -> tuple[str, dict[str, Any]] | str:
    """Change la stratégie par défaut LIÉE PAR ID d'un workspace (spec §5).

    Même protocole de garde que `apply_engine_change` : le découpage des
    documents déjà indexés change → invalidation `indexed_documents` + job
    `reindex_chunking_change` derrière confirmation. `strategy_id` NULL retire
    le binding (retour à la cascade textuelle).

    - identique → ``"no_change"``.
    - stratégie invisible (ni système ni au caller) → UnknownDefaultStrategyError.
    - 0 doc → bascule immédiate → ``("updated", {...})``.
    - >0 doc + ``confirm=False`` → lève :class:`ChunkingChangeRequiresReindex`.
    - >0 doc + ``confirm=True`` → bascule + invalidation + job.
    """
    ws_row = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name = $1", name)
    if ws_row is None:
        raise WorkspaceNotFound(name)
    workspace_id = ws_row["id"]

    if strategy_id is not None:
        visible = await config_pool.fetchval(
            "SELECT 1 FROM chunking_strategies s "
            "WHERE s.id = $1 AND s.workspace_id IS NULL "
            "AND (s.owner_id IS NULL OR s.owner_id = $2)",
            strategy_id,
            owner_id,
        )
        if visible is None:
            raise UnknownDefaultStrategyError(f"stratégie introuvable : {strategy_id}")

    current = await config_pool.fetchval(
        "SELECT default_strategy_id FROM chunking_configs WHERE workspace_id = $1",
        workspace_id,
    )
    if current == strategy_id:
        return "no_change"

    body = {
        "workspace_id": str(workspace_id),
        "default_strategy_id": str(strategy_id) if strategy_id is not None else None,
    }
    docs = await config_pool.fetchval(
        "SELECT COUNT(*) FROM indexed_documents WHERE workspace_id = $1", workspace_id
    )
    if int(docs or 0) == 0:
        await config_pool.execute(
            "UPDATE chunking_configs SET default_strategy_id=$1, updated_at=now() "
            "WHERE workspace_id=$2",
            strategy_id,
            workspace_id,
        )
        log.info("chunking.default_strategy_changed", workspace=name, mode="no_reindex")
        return ("updated", body)

    if not confirm:
        raise ChunkingChangeRequiresReindex(
            workspace=name,
            current=f"default_strategy_id={current}",
            new=f"default_strategy_id={strategy_id}",
        )

    async with config_pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE chunking_configs SET default_strategy_id=$1, updated_at=now() "
            "WHERE workspace_id=$2",
            strategy_id,
            workspace_id,
        )
        await conn.execute("DELETE FROM indexed_documents WHERE workspace_id=$1", workspace_id)
        job_row = await conn.fetchrow(
            """
            INSERT INTO index_jobs (workspace_id, triggered_by, status)
            VALUES ($1, 'reindex_chunking_change', 'pending')
            RETURNING id, triggered_by, status, files_changed, files_skipped,
                      error_message, started_at, finished_at, duration_ms
            """,
            workspace_id,
        )
    if job_row is None:
        raise RuntimeError("apply_default_strategy_change: INSERT did not RETURN")

    log.info(
        "chunking.default_strategy_changed",
        workspace=name,
        mode="reindex_triggered",
        job_id=str(job_row["id"]),
    )
    return ("reindex_triggered", _job_to_dict(job_row))
