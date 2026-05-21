"""Helper de test : insère un workspace minimal avec le nouveau schéma
(api_key_ref + api_key_fingerprint). Centralise la connaissance du
schéma pour éviter la duplication dans les tests d'intégration.
"""
from __future__ import annotations

from hashlib import sha256
from uuid import UUID

import asyncpg


async def seed_workspace(
    conn: asyncpg.Connection,
    *,
    name: str,
    api_key: str = "test-api-key",
    api_key_ref: str | None = None,
    rag_cnx: str = "postgresql://test/c",
    rag_base: str = "rag_test_b",
    # Paramètre `dek` conservé pour compatibilité d'appel — ignoré (schéma 015).
    dek: str | None = None,
) -> UUID:
    """Insère un workspace test, retourne son UUID.

    `api_key_ref` par défaut synthétique `${vault://test:<name>_apikey}`.
    `api_key_fingerprint` est le SHA-256 de `api_key` (lookup bearer auth).
    `dek` est ignoré — conservé uniquement pour que les call-sites existants
    compilent sans modification.
    """
    if api_key_ref is None:
        api_key_ref = f"${{vault://test:{name}_apikey}}"
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    row = await conn.fetchrow(
        """
        INSERT INTO workspaces
            (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base)
        VALUES
            ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        name, api_key_ref, fingerprint, rag_cnx, rag_base,
    )
    if row is None:
        raise RuntimeError("seed_workspace: INSERT did not RETURN id")
    return row["id"]
