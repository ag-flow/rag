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
    owner_id: str | None = None,
) -> UUID:
    """Insère un workspace test, retourne son UUID. owner_id None = partagé."""
    row = await conn.fetchrow(
        """
        INSERT INTO workspaces (name, rag_cnx, rag_base, owner_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        name, rag_cnx, rag_base, owner_id,
    )
    if row is None:
        raise RuntimeError("seed_workspace: INSERT did not RETURN id")
    return row["id"]


async def seed_user_api_key(
    conn: asyncpg.Connection,
    *,
    api_key: str,
    scope: str = "read_write",
    owner_id: str = "test-owner",
    name: str = "test-key",
) -> UUID:
    """Insère une clé utilisateur (hash-only) avec son niveau d'accès global.

    `scope` ∈ ('read', 'read_write', 'admin') — appliqué à tous les workspaces
    (migration 067 : les grants par workspace ont été supprimés).
    Retourne l'UUID de la clé.
    """
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    key_id = await conn.fetchval(
        """
        INSERT INTO user_api_keys (owner_id, name, fingerprint, scope)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        owner_id, name, fingerprint, scope,
    )
    return key_id
