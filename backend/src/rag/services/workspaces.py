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
from rag.secrets.refs import build_ref
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

    Étapes (cf. spec 2026-05-21-consolidate-workspace-apikeys-design.md §6.1) :
      1. Lookup dimension dans model_dimensions
      2. Vérifie que le coffre api_key_vault existe (→ VaultNotFoundForWorkspace)
      3. Eager validation de indexer.api_key_ref via Harpocrate (si présent)
      4. Génère api_key + fingerprint SHA-256 + calcule path/ref Harpocrate
      5. write_secret dans le coffre choisi (→ HarpocrateWriteFailed si échec)
      6. INSERT workspaces + indexer_configs + chunking_configs (TRANSACTION)
         Sur UniqueViolationError : delete_secret (rollback Harpocrate) + WorkspaceAlreadyExists
         Sur autre Exception : delete_secret + re-raise
      7. CREATE DATABASE rag_<name> (admin_dsn, hors transaction)
      8. CREATE EXTENSION + CREATE TABLE embeddings + INDEX ivfflat + migrations
         Sur échec : DELETE workspaces + DROP DATABASE + delete_secret (rollback Harpocrate)
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

    # 3. Eager validation de la ref indexeur (sauf si None, ex: Ollama sans auth)
    if request.indexer.api_key_ref is not None:
        await _validate_ref_via_vault(resolver, request.indexer.api_key_ref, request.api_key_vault)

    # 4. Génération api_key + fingerprint SHA-256 + ref Harpocrate
    api_key = generate_api_key()
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    path = f"wsapi_{request.name}"
    api_key_ref = build_ref(request.api_key_vault, path)

    rag_base = f"rag_{request.name}"
    rag_cnx = derive_workspace_dsn(admin_dsn, rag_base)

    # 5. Écriture du secret workspace dans Harpocrate
    async with config_pool.acquire() as conn:
        await harpocrate_vaults_service.write_secret(
            conn,
            vault_name=request.api_key_vault,
            path=path,
            value=api_key,
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
                request.indexer.api_key_ref,
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
        # Rollback Harpocrate : le secret a été écrit mais le workspace n'existe pas
        async with config_pool.acquire() as conn:
            await harpocrate_vaults_service.delete_secret(
                conn, vault_name=request.api_key_vault, path=path
            )
        raise WorkspaceAlreadyExists(request.name) from e
    except Exception:
        # Rollback Harpocrate sur toute autre erreur DB
        async with config_pool.acquire() as conn:
            await harpocrate_vaults_service.delete_secret(
                conn, vault_name=request.api_key_vault, path=path
            )
        raise

    # 7. + 8. DDL workspace, avec compensation si erreur
    try:
        await create_workspace_database(admin_dsn, rag_base)
        await create_embeddings_table(rag_cnx, dimension=dimension)
        # 8bis. Initialise workspace_schema_migrations + applique 001 (idempotent
        # sur la table fraîchement créée par create_embeddings_table).
        await apply_pending(rag_cnx)
    except Exception:
        log.exception(
            "workspace.create.ddl_failed_rolling_back",
            workspace=request.name,
        )
        # Compensation : drop base, DELETE config, delete secret Harpocrate
        await drop_workspace_database(admin_dsn, rag_base)
        async with config_pool.acquire() as conn:
            await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_row["id"])
        async with config_pool.acquire() as conn:
            await harpocrate_vaults_service.delete_secret(
                conn, vault_name=request.api_key_vault, path=path
            )
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
    api_key_dek: str,
    apikey_cache: ApiKeyCache | None = None,
    max_attempts: int = 3,
) -> str:
    """Régénère une api_key pour le workspace, retourne la nouvelle en clair.

    Boucle bornée à max_attempts pour gérer la collision théorique du
    fingerprint (proba ~2⁻¹²⁸ par paire). Lève RuntimeError au-delà.
    Lève WorkspaceNotFound si le workspace n'existe pas.

    Invalide instantanément l'ancienne clé (UPDATE atomique chiffré) et,
    si un cache est fourni, supprime toute entrée en cache pour ce workspace
    afin que les requêtes suivantes refassent la vérification.
    """
    row = await fetch_one(config_pool, "SELECT id FROM workspaces WHERE name=$1", name)
    if row is None:
        raise WorkspaceNotFound(name)

    last_err: asyncpg.UniqueViolationError | None = None
    for _ in range(max_attempts):
        new_key = generate_api_key()
        fingerprint = sha256(new_key.encode("utf-8")).hexdigest()
        try:
            async with config_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE workspaces SET "
                    "api_key_encrypted = pgp_sym_encrypt($1::text, $2::text)::bytea, "
                    "api_key_fingerprint = $3, "
                    "updated_at = now() "
                    "WHERE id = $4",
                    new_key,
                    api_key_dek,
                    fingerprint,
                    row["id"],
                )
            break
        except asyncpg.UniqueViolationError as e:
            last_err = e
            continue
    else:
        raise RuntimeError(f"fingerprint collision after {max_attempts} attempts") from last_err

    if apikey_cache is not None:
        # FIXME(T5) : invalidate attend la ref vault "${vault://...}", pas le name.
        # Refactoré en T5.
        apikey_cache.invalidate(name)

    log.info("workspace.apikey_rotated", name=name)
    return new_key


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
