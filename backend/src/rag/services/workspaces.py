from __future__ import annotations

from typing import Protocol

import asyncpg
import structlog

from rag.api.errors import (
    RefNotFoundInVault,
    VaultUnreachable,
    WorkspaceAlreadyExists,
)
from rag.db.helpers import transaction
from rag.db.workspace_schema import (
    create_embeddings_table,
    create_workspace_database,
    derive_workspace_dsn,
    drop_workspace_database,
)
from rag.schemas.admin import WorkspaceCreateRequest
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
