from __future__ import annotations

import json

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from rag.indexer.chunking import Chunk

log = structlog.get_logger(__name__)


async def upsert_chunks(
    workspace_pool: asyncpg.Pool,
    *,
    path: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> int:
    """Remplace tous les chunks d'un path par une nouvelle liste.

    Strategie : DELETE FROM embeddings WHERE path=$1 puis INSERT batch (content
    + embedding + metadata jsonb), dans une transaction unique pour l'atomicite.

    Pre-condition : `len(chunks) == len(embeddings)` - sinon ValueError.
    Retourne le nombre de chunks inseres.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have the same length"
        )
    if not chunks:
        # Cas degenere : juste supprimer ce qui existait pour ce path.
        await delete_chunks_for_path(workspace_pool, path)
        return 0

    async with workspace_pool.acquire() as conn, conn.transaction():
        # pgvector enregistre les codecs vector sur la connexion ; si le pool
        # n'a pas ete cree avec init=register_vector, on le fait ici.
        await register_vector(conn)
        await conn.execute(
            "DELETE FROM embeddings WHERE path=$1",
            path,
        )
        records = [
            (path, idx, chunk.content, embedding, json.dumps(dict(chunk.metadata)))
            for idx, (chunk, embedding) in enumerate(
                zip(chunks, embeddings, strict=True),
            )
        ]
        await conn.executemany(
            "INSERT INTO embeddings (path, chunk_index, content, embedding, metadata) "
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
            records,
        )

    log.info(
        "workspace_embeddings.upserted",
        path=path,
        chunks=len(chunks),
    )
    return len(chunks)


async def delete_chunks_for_path(
    workspace_pool: asyncpg.Pool,
    path: str,
) -> int:
    """DELETE FROM embeddings WHERE path=$1. Retourne nombre supprime."""
    async with workspace_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM embeddings WHERE path=$1",
            path,
        )
    count = int(result.split()[-1])
    if count > 0:
        log.info(
            "workspace_embeddings.deleted",
            path=path,
            count=count,
        )
    return count


async def delete_path(workspace_pool: asyncpg.Pool, path: str) -> None:
    """Alias semantique de delete_chunks_for_path utilise par RealIndexer."""
    await delete_chunks_for_path(workspace_pool, path)
