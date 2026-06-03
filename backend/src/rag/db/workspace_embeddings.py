from __future__ import annotations

import json
from typing import Literal

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
    strategy: Literal["replace", "append"] = "replace",
) -> int:
    """Indexe les chunks d'un path selon la stratégie donnée.

    replace (défaut) : DELETE WHERE path puis INSERT — comportement d'origine.
    append           : INSERT uniquement, pas de DELETE. Les anciennes versions
                       sont conservées et distinguées par leur indexed_at.

    Pré-condition : len(chunks) == len(embeddings), sinon ValueError.
    Retourne le nombre de chunks insérés.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have the same length"
        )
    if not chunks:
        if strategy == "replace":
            await delete_chunks_for_path(workspace_pool, path)
        return 0

    async with workspace_pool.acquire() as conn, conn.transaction():
        await register_vector(conn)
        if strategy == "replace":
            await conn.execute("DELETE FROM embeddings WHERE path=$1", path)
            records = [
                (path, idx, chunk.content, embedding, json.dumps(dict(chunk.metadata)))
                for idx, (chunk, embedding) in enumerate(
                    zip(chunks, embeddings, strict=True),
                )
            ]
        else:
            raw = await conn.fetchval(
                "SELECT COALESCE(MAX(chunk_index), -1) FROM embeddings WHERE path=$1",
                path,
            )
            max_idx: int = raw if raw is not None else -1
            records = [
                (
                    path,
                    max_idx + 1 + idx,
                    chunk.content,
                    embedding,
                    json.dumps(dict(chunk.metadata)),
                )
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
        strategy=strategy,
    )
    return len(chunks)


async def delete_chunks_for_path(
    workspace_pool: asyncpg.Pool,
    path: str,
) -> int:
    """DELETE FROM embeddings WHERE path=$1. Retourne nombre supprimé."""
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
    """Alias sémantique de delete_chunks_for_path utilisé par RealIndexer."""
    await delete_chunks_for_path(workspace_pool, path)
