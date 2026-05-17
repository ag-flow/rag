"""Helper de test : insère un workspace minimal avec le nouveau schéma
(api_key_encrypted + api_key_fingerprint). Centralise la connaissance du
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
    dek: str = "x" * 32,
    rag_cnx: str = "postgresql://test/c",
    rag_base: str = "rag_test_b",
) -> UUID:
    """Insère un workspace test, retourne son UUID.

    `api_key` est chiffrée via pgp_sym_encrypt(api_key, dek) et son
    fingerprint SHA-256 est inséré dans la colonne dédiée.
    """
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    row = await conn.fetchrow(
        """
        INSERT INTO workspaces
            (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base)
        VALUES
            ($1, pgp_sym_encrypt($2::text, $3::text)::bytea, $4, $5, $6)
        RETURNING id
        """,
        name, api_key, dek, fingerprint, rag_cnx, rag_base,
    )
    if row is None:
        raise RuntimeError("seed_workspace: INSERT did not RETURN id")
    return row["id"]
