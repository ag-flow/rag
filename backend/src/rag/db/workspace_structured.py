from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ParentRow:
    section_key: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChildRow:
    chunk_hash: str
    embed_text: str
    parent_key: str
    chunk_index: int
    metadata: Mapping[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None  # None = chunk conservé (déjà embeddé)


@dataclass(frozen=True)
class ChildrenPlan:
    """Plan de diff incrémental (ADR 0001 §5)."""

    new_hashes: list[str]
    kept_hashes: list[str]
    deleted_hashes: list[str]


def plan_children(existing_hashes: set[str], doc_hashes: list[str]) -> ChildrenPlan:
    """Partitionne les chunks du nouveau document vs ce qui est en base.

    - `new_hashes`     : à embedder + insérer (absents en base).
    - `kept_hashes`    : déjà embeddés, on les garde (pas de ré-embed).
    - `deleted_hashes` : en base mais absents du nouveau doc → à supprimer.

    Déduplique les hashes identiques au sein du doc (deux chunks au texte
    embeddé identique → une seule ligne, dédoublonnage idempotent).
    """
    seen: set[str] = set()
    new: list[str] = []
    kept: list[str] = []
    for h in doc_hashes:
        if h in seen:
            continue
        seen.add(h)
        if h in existing_hashes:
            kept.append(h)
        else:
            new.append(h)
    deleted = [h for h in existing_hashes if h not in seen]
    return ChildrenPlan(new_hashes=new, kept_hashes=kept, deleted_hashes=deleted)


async def load_existing_chunk_hashes(workspace_pool: asyncpg.Pool, path: str) -> set[str]:
    """Hashes des chunks structurés déjà indexés pour `path`."""
    async with workspace_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT chunk_hash FROM embeddings WHERE path=$1 AND chunk_hash IS NOT NULL",
            path,
        )
    return {r["chunk_hash"] for r in rows}


async def upsert_structured(
    workspace_pool: asyncpg.Pool,
    *,
    path: str,
    parents: list[ParentRow],
    children: list[ChildRow],
) -> dict[str, int]:
    """Upsert structure-aware d'un `path` : sections parentes + enfants, en diff.

    - supprime les anciennes lignes legacy (chunk_hash NULL) de ce path ;
    - supprime les enfants dont le hash a disparu ;
    - upsert les sections (id stable via ON CONFLICT) ;
    - insère les enfants `embedding != None`, met à jour l'ordre/lien des
      enfants conservés (`embedding == None`).

    Pré-condition : tout enfant conservé existe déjà (hash présent en base).
    """
    deduped = _dedupe_children(children)
    current_hashes = [c.chunk_hash for c in deduped]
    current_keys = [p.section_key for p in parents]

    async with workspace_pool.acquire() as conn, conn.transaction():
        await register_vector(conn)

        await conn.execute(
            "DELETE FROM embeddings WHERE path=$1 AND chunk_hash IS NULL", path
        )
        deleted = await conn.execute(
            "DELETE FROM embeddings WHERE path=$1 AND chunk_hash IS NOT NULL "
            "AND chunk_hash <> ALL($2::text[])",
            path,
            current_hashes,
        )

        key_to_id = await _upsert_sections(conn, path, parents)
        await conn.execute(
            "DELETE FROM sections WHERE path=$1 AND section_key <> ALL($2::text[])",
            path,
            current_keys,
        )

        inserted = kept = 0
        for child in deduped:
            section_id = key_to_id[child.parent_key]
            meta = json.dumps(dict(child.metadata))
            if child.embedding is not None:
                await conn.execute(
                    "INSERT INTO embeddings "
                    "(path, chunk_index, content, embedding, metadata, chunk_hash, section_id) "
                    "VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7) "
                    "ON CONFLICT (path, chunk_hash) WHERE chunk_hash IS NOT NULL "
                    "DO UPDATE SET chunk_index=EXCLUDED.chunk_index, "
                    "section_id=EXCLUDED.section_id, metadata=EXCLUDED.metadata, "
                    "content=EXCLUDED.content, embedding=EXCLUDED.embedding",
                    path,
                    child.chunk_index,
                    child.embed_text,
                    child.embedding,
                    meta,
                    child.chunk_hash,
                    section_id,
                )
                inserted += 1
            else:
                await conn.execute(
                    "UPDATE embeddings SET chunk_index=$2, section_id=$3, metadata=$4::jsonb "
                    "WHERE path=$1 AND chunk_hash=$5",
                    path,
                    child.chunk_index,
                    section_id,
                    meta,
                    child.chunk_hash,
                )
                kept += 1

    result = {
        "inserted": inserted,
        "kept": kept,
        "deleted": int(deleted.split()[-1]),
        "sections": len(parents),
    }
    log.info("workspace_structured.upserted", path=path, **result)
    return result


def _dedupe_children(children: list[ChildRow]) -> list[ChildRow]:
    seen: set[str] = set()
    out: list[ChildRow] = []
    for child in children:
        if child.chunk_hash in seen:
            continue
        seen.add(child.chunk_hash)
        out.append(child)
    return out


async def _upsert_sections(
    conn: asyncpg.Connection,
    path: str,
    parents: list[ParentRow],
) -> dict[str, int]:
    key_to_id: dict[str, int] = {}
    for parent in parents:
        section_id = await conn.fetchval(
            "INSERT INTO sections (path, section_key, content, metadata) "
            "VALUES ($1,$2,$3,$4::jsonb) "
            "ON CONFLICT (path, section_key) DO UPDATE SET "
            "content=EXCLUDED.content, metadata=EXCLUDED.metadata, indexed_at=now() "
            "RETURNING id",
            path,
            parent.section_key,
            parent.content,
            json.dumps(dict(parent.metadata)),
        )
        key_to_id[parent.section_key] = section_id
    return key_to_id
