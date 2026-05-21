from __future__ import annotations

from hashlib import sha256
from typing import Protocol

import asyncpg
import structlog

from rag.api.errors import (
    RefNotFoundInVault,
    VaultNotFoundForWorkspace,
    VaultUnreachable,
    WorkspaceAlreadyExists,
    WorkspaceNotFound,
)
from rag.auth.workspace_auth import ApiKeyCache
from rag.db.helpers import fetch_all, fetch_one, transaction
from rag.db.workspace_migrations import apply_pending
from rag.db.workspace_schema import (
    create_embeddings_table,
    create_workspace_database,
    derive_workspace_dsn,
    drop_workspace_database,
)
from rag.schemas.admin import WorkspaceCreateRequest, WorkspacePatchRequest
from rag.secrets.refs import build_ref, parse_ref
from rag.secrets.resolver import VaultLookupFailed
from rag.services.apikey import generate_api_key
from rag.services.harpocrate_vaults import HarpocrateVaultsService
from rag.services.models import get_dimension_or_raise

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    async def resolve_with_retry(self, ref: str) -> str: ...


def to_vault_ref(logical_key: str, vault_name: str) -> str:
    """Convertit une clé logique simple en ref ``${vault://<vault_name>:<logical>}``.

    `vault_name` est résolu dynamiquement à chaque appel (via
    `HarpocrateClientProvider.get_default_vault_name()` côté router) — plus de
    hardcodage. Le service stocke toujours la clé logique simple en base
    (`"openai_embedding_key"`), mais le `SecretResolver` attend le formalisme
    déclaratif. Cette fonction fait le pont.
    """
    return build_ref(vault_name, logical_key)


async def _validate_ref_via_vault(
    resolver: _ResolverProtocol,
    logical_key: str,
    vault_name: str,
) -> None:
    """Eager validation : la ref doit résoudre. Sinon : 422 ou 503 selon la cause."""
    ref = to_vault_ref(logical_key, vault_name)
    try:
        await resolver.resolve_with_retry(ref)
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
    harpocrate_vaults_service: HarpocrateVaultsService,
) -> dict[str, str]:
    """Crée un workspace + sa base pgvector + sa table embeddings.

    Étapes :
      1. Lookup dimension dans model_dimensions
      2. Vérifie que le coffre api_key_vault existe (→ VaultNotFoundForWorkspace)
      3. Écrit l'api_key indexeur dans Harpocrate si fournie
         Path convention : <workspace_name>/<provider>/key (ex: wrk1/openai/key)
      4. Génère api_key MCP + fingerprint SHA-256 + calcule path/ref Harpocrate
      5. write_secret workspace dans le coffre choisi (→ HarpocrateWriteFailed si échec)
      6. INSERT workspaces + indexer_configs + chunking_configs (TRANSACTION)
         Sur UniqueViolationError : delete_secret x2 (rollback Harpocrate) + WorkspaceAlreadyExists
         Sur autre Exception : delete_secret x2 + re-raise
      7. CREATE DATABASE rag_<name> (admin_dsn, hors transaction)
      8. CREATE EXTENSION + CREATE TABLE embeddings + INDEX ivfflat + migrations
         Sur échec : DELETE workspaces + DROP DATABASE + delete_secret x2 (rollback Harpocrate)
      9. Retour { id, name, api_key, api_key_ref, created_at } — api_key en clair UNIQUE
    """
    # 1. Dimension du modèle
    dimension = await get_dimension_or_raise(
        config_pool, provider=request.indexer.provider, model=request.indexer.model
    )

    # 2. Vérification existence du coffre cible
    async with config_pool.acquire() as conn:
        vault = await harpocrate_vaults_service.get_by_name(conn, request.api_key_vault)
    if vault is None:
        raise VaultNotFoundForWorkspace(request.api_key_vault)

    # 3. Stockage de l'api_key indexeur dans Harpocrate (si fournie)
    indexer_path: str | None = None
    indexer_api_key_ref: str | None = None
    if request.indexer.api_key is not None:
        indexer_path = f"{request.name}/{request.indexer.provider}/key"
        async with config_pool.acquire() as conn:
            await harpocrate_vaults_service.write_secret(
                conn,
                vault_name=request.api_key_vault,
                path=indexer_path,
                value=request.indexer.api_key,
            )
        indexer_api_key_ref = build_ref(request.api_key_vault, indexer_path)

    # 4. Génération api_key MCP + fingerprint SHA-256 + ref Harpocrate
    api_key = generate_api_key()
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    ws_path = f"wsapi_{request.name}"
    api_key_ref = build_ref(request.api_key_vault, ws_path)

    rag_base = f"rag_{request.name}"
    rag_cnx = derive_workspace_dsn(admin_dsn, rag_base)

    # 5. Écriture du secret workspace dans Harpocrate
    async with config_pool.acquire() as conn:
        await harpocrate_vaults_service.write_secret(
            conn,
            vault_name=request.api_key_vault,
            path=ws_path,
            value=api_key,
        )

    async def _rollback_harpocrate() -> None:
        async with config_pool.acquire() as conn:
            await harpocrate_vaults_service.delete_secret(
                conn, vault_name=request.api_key_vault, path=ws_path
            )
        if indexer_path is not None:
            async with config_pool.acquire() as conn:
                await harpocrate_vaults_service.delete_secret(
                    conn, vault_name=request.api_key_vault, path=indexer_path
                )

    # 6. INSERT workspaces + indexer_configs + chunking_configs (TRANSACTION)
    ws_row = None
    try:
        async with transaction(config_pool) as conn:
            ws_row = await conn.fetchrow(
                """
                INSERT INTO workspaces
                    (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base)
                VALUES
                    ($1, $2, $3, $4, $5)
                RETURNING id, created_at
                """,
                request.name,
                api_key_ref,
                fingerprint,
                rag_cnx,
                rag_base,
            )
            if ws_row is None:
                raise RuntimeError("unexpected None from RETURNING")
            await conn.execute(
                """
                INSERT INTO indexer_configs
                    (workspace_id, provider, model, api_key_ref, base_url, dimension)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                ws_row["id"],
                request.indexer.provider,
                request.indexer.model,
                indexer_api_key_ref,
                request.indexer.base_url,
                dimension,
            )
            await conn.execute(
                """
                INSERT INTO chunking_configs
                    (workspace_id, strategy, max_chars, min_chars, overlap_chars, extras)
                VALUES ($1, 'paragraph', 2000, 200, 200, '{}'::jsonb)
                """,
                ws_row["id"],
            )
    except asyncpg.UniqueViolationError as e:
        await _rollback_harpocrate()
        raise WorkspaceAlreadyExists(request.name) from e
    except Exception:
        await _rollback_harpocrate()
        raise

    # 7. + 8. DDL workspace, avec compensation si erreur
    try:
        await create_workspace_database(admin_dsn, rag_base)
        await create_embeddings_table(rag_cnx, dimension=dimension)
        await apply_pending(rag_cnx)
    except Exception:
        log.exception(
            "workspace.create.ddl_failed_rolling_back",
            workspace=request.name,
        )
        await drop_workspace_database(admin_dsn, rag_base)
        async with config_pool.acquire() as conn:
            await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_row["id"])
        await _rollback_harpocrate()
        raise

    log.info("workspace.created", name=request.name, dimension=dimension)

    return {
        "id": str(ws_row["id"]),
        "name": request.name,
        "api_key": api_key,
        "api_key_ref": api_key_ref,
        "created_at": ws_row["created_at"].isoformat(),
    }


async def list_workspaces(config_pool: asyncpg.Pool) -> list[dict[str, object]]:
    """Liste tous les workspaces avec leurs compteurs (0/null en M2)."""
    rows = await fetch_all(
        config_pool,
        """
        SELECT
            w.id, w.name, w.created_at,
            ic.provider, ic.model, ic.api_key_ref, ic.base_url,
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
            ic.provider, ic.model, ic.api_key_ref, ic.base_url,
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
    default_vault_name: str = "rag",
) -> None:
    """Met à jour `indexer.api_key_ref` (seul champ patchable en M2).

    Eager validation de la nouvelle ref via Harpocrate avant UPDATE.
    Lève WorkspaceNotFound si le workspace n'existe pas.
    """
    new_ref = request.indexer.api_key_ref
    await _validate_ref_via_vault(resolver, new_ref, default_vault_name)

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


async def rotate_apikey(
    *,
    name: str,
    config_pool: asyncpg.Pool,
    harpocrate_vaults_service: HarpocrateVaultsService,
    apikey_cache: ApiKeyCache,
) -> dict[str, str]:
    """Rotation api_key MCP d'un workspace.

    Étapes :
      1. Lit le `api_key_ref` actuel du workspace.
      2. Parse la ref pour obtenir (vault_name, path).
      3. Génère nouvelle api_key + fingerprint.
      4. Écrit la nouvelle valeur dans Harpocrate (upsert).
      5. UPDATE fingerprint en DB.
      6. Invalide le cache mémoire pour ce ref.
      7. Retourne la nouvelle api_key en clair (one-shot).
    """
    row = await config_pool.fetchrow(
        "SELECT api_key_ref FROM workspaces WHERE name = $1",
        name,
    )
    if row is None:
        raise WorkspaceNotFound(name)

    api_key_ref: str = row["api_key_ref"]
    vault_name, path = parse_ref(api_key_ref)

    new_api_key = generate_api_key()
    new_fingerprint = sha256(new_api_key.encode("utf-8")).hexdigest()

    # 4. Écrit AVANT update DB. write_secret demande une Connection.
    async with config_pool.acquire() as conn:
        await harpocrate_vaults_service.write_secret(
            conn,
            vault_name=vault_name,
            path=path,
            value=new_api_key,
        )

    # 5. Update fingerprint en DB
    await config_pool.execute(
        "UPDATE workspaces SET api_key_fingerprint = $1 WHERE name = $2",
        new_fingerprint,
        name,
    )

    # 6. Invalide le cache (référence complète)
    apikey_cache.invalidate(api_key_ref)

    log.info("workspace.apikey_rotated", name=name)
    return {"api_key": new_api_key}


def _to_workspace_dict(row: asyncpg.Record) -> dict[str, object]:
    last_indexed = row["last_indexed_at"]
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "indexer": {
            "provider": row["provider"],
            "model": row["model"],
            "api_key_ref": row["api_key_ref"],
            "base_url": row["base_url"],
        },
        "sources_count": int(row["sources_count"]),
        "documents_count": int(row["documents_count"]),
        "last_indexed_at": last_indexed.isoformat() if last_indexed is not None else None,
        "created_at": row["created_at"].isoformat(),
    }
