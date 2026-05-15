from __future__ import annotations

from typing import Protocol

import asyncpg
import structlog

from rag.api.errors import (
    RefNotFoundInVault,
    VaultUnreachable,
    WorkspaceAlreadyExists,
    WorkspaceNotFound,
)
from rag.db.helpers import fetch_all, fetch_one, transaction
from rag.db.workspace_schema import (
    create_embeddings_table,
    create_workspace_database,
    derive_workspace_dsn,
    drop_workspace_database,
)
from rag.schemas.admin import WorkspaceCreateRequest, WorkspacePatchRequest
from rag.secrets.resolver import VaultLookupFailed
from rag.services.apikey import generate_api_key, hash_api_key
from rag.services.models import get_dimension_or_raise

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


def to_vault_ref(logical_key: str, *, vault_id: str = "rag") -> str:
    """Convertit une clé logique simple en ref `${vault://<id>:<logical>}`.

    Le service stocke en base la clé logique simple (`"openai_embedding_key"`)
    pour rester aligné spec 06-secrets.md. Mais le `SecretResolver` M1 attend le
    formalisme déclaratif `${vault://id:path}`. Cette fonction fait le pont.
    """
    return f"${{vault://{vault_id}:{logical_key}}}"


def _validate_ref_via_vault(resolver: _ResolverProtocol, logical_key: str) -> None:
    """Eager validation : la ref doit résoudre. Sinon : 422 ou 503 selon la cause."""
    ref = to_vault_ref(logical_key)
    try:
        resolver.resolve_with_retry(ref)
    except VaultLookupFailed as e:
        raise RefNotFoundInVault(logical_key) from e
    except (ConnectionError, TimeoutError) as e:
        raise VaultUnreachable() from e


async def create_workspace(
    *,
    request: WorkspaceCreateRequest,
    config_pool: asyncpg.Pool,
    admin_dsn: str,
    resolver: _ResolverProtocol,
) -> dict[str, str]:
    """Crée un workspace + sa base pgvector + sa table embeddings.

    Étapes (cf. spec 2026-05-15-M2-api-admin-design.md, Flow A) :
      1. Lookup dimension dans model_dimensions
      2. Eager validation de indexer.api_key_ref via Harpocrate
      3. Génère api_key + hash bcrypt
      4. INSERT workspaces + indexer_configs (TRANSACTION config_pool)
      5. CREATE DATABASE rag_<name> (admin_dsn, hors transaction)
      6. CREATE EXTENSION + CREATE TABLE embeddings + INDEX ivfflat
      7. Retour { id, name, api_key, created_at } — api_key en clair UNIQUE
    Compensation sur échec étapes 5/6 : DELETE workspaces + DROP DATABASE.
    """
    # 1. Dimension du modèle
    dimension = await get_dimension_or_raise(
        config_pool, provider=request.indexer.provider, model=request.indexer.model
    )

    # 2. Eager validation de la ref Harpocrate (sauf si None, ex: Ollama sans auth)
    if request.indexer.api_key_ref is not None:
        _validate_ref_via_vault(resolver, request.indexer.api_key_ref)

    # 3. Génération api_key
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    rag_base = f"rag_{request.name}"
    rag_cnx = derive_workspace_dsn(admin_dsn, rag_base)

    # 4. INSERT workspaces + indexer_configs (TRANSACTION)
    try:
        async with transaction(config_pool) as conn:
            ws_row = await conn.fetchrow(
                """
                INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base)
                VALUES ($1, $2, $3, $4)
                RETURNING id, created_at
                """,
                request.name,
                api_key_hash,
                rag_cnx,
                rag_base,
            )
            if ws_row is None:
                raise RuntimeError("unexpected None from RETURNING")
            await conn.execute(
                """
                INSERT INTO indexer_configs (workspace_id, provider, model, api_key_ref, dimension)
                VALUES ($1, $2, $3, $4, $5)
                """,
                ws_row["id"],
                request.indexer.provider,
                request.indexer.model,
                request.indexer.api_key_ref,
                dimension,
            )
    except asyncpg.UniqueViolationError as e:
        raise WorkspaceAlreadyExists(request.name) from e

    # 5. + 6. DDL workspace, avec compensation si erreur
    try:
        await create_workspace_database(admin_dsn, rag_base)
        await create_embeddings_table(rag_cnx, dimension=dimension)
    except Exception:
        log.exception(
            "workspace.create.ddl_failed_rolling_back",
            workspace=request.name,
        )
        # Compensation : retire le workspace en base config + drop base éventuelle.
        await drop_workspace_database(admin_dsn, rag_base)
        async with config_pool.acquire() as conn:
            await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_row["id"])
        raise

    log.info("workspace.created", name=request.name, dimension=dimension)

    return {
        "id": str(ws_row["id"]),
        "name": request.name,
        "api_key": api_key,
        "created_at": ws_row["created_at"].isoformat(),
    }


async def list_workspaces(config_pool: asyncpg.Pool) -> list[dict[str, object]]:
    """Liste tous les workspaces avec leurs compteurs (0/null en M2)."""
    rows = await fetch_all(
        config_pool,
        """
        SELECT
            w.id, w.name, w.created_at,
            ic.provider, ic.model, ic.api_key_ref,
            (SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = w.id) AS sources_count,
            (SELECT COUNT(*) FROM indexed_documents WHERE workspace_id = w.id) AS documents_count,
            (SELECT MAX(indexed_at) FROM indexed_documents WHERE workspace_id = w.id)
                AS last_indexed_at
        FROM workspaces w
        LEFT JOIN indexer_configs ic ON ic.workspace_id = w.id
        ORDER BY w.created_at
        """,
    )
    return [_to_workspace_dict(r) for r in rows]


async def get_workspace(config_pool: asyncpg.Pool, *, name: str) -> dict[str, object]:
    """Détail d'un workspace. Lève WorkspaceNotFound si miss."""
    row = await fetch_one(
        config_pool,
        """
        SELECT
            w.id, w.name, w.created_at,
            ic.provider, ic.model, ic.api_key_ref,
            (SELECT COUNT(*) FROM workspace_sources WHERE workspace_id = w.id) AS sources_count,
            (SELECT COUNT(*) FROM indexed_documents WHERE workspace_id = w.id) AS documents_count,
            (SELECT MAX(indexed_at) FROM indexed_documents WHERE workspace_id = w.id)
                AS last_indexed_at
        FROM workspaces w
        LEFT JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise WorkspaceNotFound(name)
    return _to_workspace_dict(row)


async def patch_workspace(
    *,
    name: str,
    request: WorkspacePatchRequest,
    config_pool: asyncpg.Pool,
    resolver: _ResolverProtocol,
) -> None:
    """Met à jour `indexer.api_key_ref` (seul champ patchable en M2).

    Eager validation de la nouvelle ref via Harpocrate avant UPDATE.
    Lève WorkspaceNotFound si le workspace n'existe pas.
    """
    new_ref = request.indexer.api_key_ref
    _validate_ref_via_vault(resolver, new_ref)

    async with config_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM workspaces WHERE name=$1", name)
        if row is None:
            raise WorkspaceNotFound(name)
        await conn.execute(
            "UPDATE indexer_configs SET api_key_ref=$1 WHERE workspace_id=$2",
            new_ref,
            row["id"],
        )
        await conn.execute("UPDATE workspaces SET updated_at=now() WHERE id=$1", row["id"])

    log.info("workspace.patched", name=name, field="api_key_ref")


async def delete_workspace(*, name: str, config_pool: asyncpg.Pool, admin_dsn: str) -> None:
    """Supprime le workspace : DROP DATABASE puis DELETE config (CASCADE).

    Idempotent : DROP DATABASE IF EXISTS ne lève pas si la base est absente.
    Si le workspace n'est pas en config DB → WorkspaceNotFound (404).
    """
    row = await fetch_one(config_pool, "SELECT id, rag_base FROM workspaces WHERE name=$1", name)
    if row is None:
        raise WorkspaceNotFound(name)

    await drop_workspace_database(admin_dsn, row["rag_base"])

    async with config_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces WHERE id=$1", row["id"])

    log.info("workspace.deleted", name=name)


def _to_workspace_dict(row: asyncpg.Record) -> dict[str, object]:
    last_indexed = row["last_indexed_at"]
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "indexer": {
            "provider": row["provider"],
            "model": row["model"],
            "api_key_ref": row["api_key_ref"],
        },
        "sources_count": int(row["sources_count"]),
        "documents_count": int(row["documents_count"]),
        "last_indexed_at": last_indexed.isoformat() if last_indexed is not None else None,
        "created_at": row["created_at"].isoformat(),
    }
