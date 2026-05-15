from __future__ import annotations

import re
from hashlib import sha256
from uuid import UUID

import asyncpg
import structlog

from rag.api.errors import InvalidPath
from rag.indexer.protocol import IndexerProtocol
from rag.schemas.workspace import (
    PushIndexedResponse,
    PushRequest,
    PushResponse,
    PushSkippedResponse,
)

log = structlog.get_logger(__name__)

_PATH_MAX_LEN = 1024
_BAD_SEGMENT = re.compile(r"(^|/)\.\.(/|$)")


def normalize_path(raw: str) -> str:
    """Normalise et valide un path POSIX relatif.

    - remplace ``\\`` par ``/``
    - rejette : NUL byte, leading ``/``, segments ``.``, vide, > 1024 chars
    """
    if "\x00" in raw:
        raise InvalidPath("path_contains_nul")
    p = raw.replace("\\", "/")
    if p.startswith("/"):
        raise InvalidPath("path_must_be_relative")
    if _BAD_SEGMENT.search(p):
        raise InvalidPath("path_traversal_forbidden")
    if not p or len(p) > _PATH_MAX_LEN:
        raise InvalidPath("path_invalid_length")
    return p


async def push_document(
    *,
    payload: PushRequest,
    workspace_id: UUID,
    indexer_used: str,
    config_pool: asyncpg.Pool,
    indexer: IndexerProtocol,
) -> PushResponse:
    """Orchestre un push synchrone : normalize → dedup → index.

    Pré-déduplication sur ``indexed_documents.content_hash`` : évite
    l'appel embedding si le contenu est identique au dernier indexé.
    Sinon délègue à ``indexer.index_file(...)`` qui fait
    chunk + embed + upsert pgvector + UPDATE indexed_documents.
    """
    norm_path = normalize_path(payload.path)
    content_hash = "sha256:" + sha256(payload.content.encode("utf-8")).hexdigest()

    existing = await config_pool.fetchval(
        "SELECT content_hash FROM indexed_documents WHERE workspace_id = $1 AND path = $2",
        workspace_id,
        norm_path,
    )
    if existing == content_hash:
        log.info(
            "push.skipped",
            workspace_id=str(workspace_id),
            path=norm_path,
            reason="content_unchanged",
        )
        return PushSkippedResponse(path=norm_path)

    chunks = await indexer.index_file(
        workspace_id=workspace_id,
        path=norm_path,
        content=payload.content,
        content_hash=content_hash,
        indexer_used=indexer_used,
    )
    log.info(
        "push.indexed",
        workspace_id=str(workspace_id),
        path=norm_path,
        chunks=chunks,
        hash=content_hash,
    )
    return PushIndexedResponse(path=norm_path, chunks=chunks, hash=content_hash)
