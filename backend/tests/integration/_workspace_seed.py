"""Helpers de test : insèrent un workspace minimal et des clés API utilisateur
avec le schéma courant. Centralisent la connaissance du schéma pour éviter la
duplication dans les tests d'intégration.
"""
from __future__ import annotations

from hashlib import sha256
from uuid import UUID

import asyncpg


async def seed_workspace(
    conn: asyncpg.Connection,
    *,
    name: str,
    # Paramètres conservés pour compatibilité d'appel — ignorés : les colonnes
    # api_key_ref / api_key_fingerprint ont été retirées de `workspaces`
    # (migration 033) et les clés d'accès sont désormais au niveau utilisateur
    # (migration 053, cf. seed_user_api_key).
    api_key: str | None = None,
    api_key_ref: str | None = None,
    rag_cnx: str = "postgresql://test/c",
    rag_base: str = "rag_test_b",
    dek: str | None = None,
) -> UUID:
    """Insère un workspace test, retourne son UUID."""
    row = await conn.fetchrow(
        """
        INSERT INTO workspaces (name, rag_cnx, rag_base)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        name, rag_cnx, rag_base,
    )
    if row is None:
        raise RuntimeError("seed_workspace: INSERT did not RETURN id")
    return row["id"]


async def seed_user_api_key(
    conn: asyncpg.Connection,
    *,
    api_key: str,
    grants: list[tuple[UUID, bool, bool]],
    owner_id: str = "test-owner",
    name: str = "test-key",
) -> UUID:
    """Insère une clé utilisateur (hash-only) + ses grants.

    `grants` : liste de tuples (workspace_id, can_read, can_write).
    Retourne l'UUID de la clé.
    """
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    key_id = await conn.fetchval(
        """
        INSERT INTO user_api_keys (owner_id, name, fingerprint)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        owner_id, name, fingerprint,
    )
    for ws_id, can_read, can_write in grants:
        await conn.execute(
            """
            INSERT INTO user_api_key_workspaces
                (api_key_id, workspace_id, can_read, can_write)
            VALUES ($1, $2, $3, $4)
            """,
            key_id, ws_id, can_read, can_write,
        )
    return key_id
