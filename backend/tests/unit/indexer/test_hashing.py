from __future__ import annotations

from rag.indexer.chunking.hashing import compute_chunk_hash


class TestComputeChunkHash:
    def test_prefixed_sha256(self) -> None:
        h = compute_chunk_hash("hello")
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_idempotent(self) -> None:
        assert compute_chunk_hash("même contenu") == compute_chunk_hash("même contenu")

    def test_sensitive_to_breadcrumb(self) -> None:
        # un changement de breadcrumb change le texte embeddé → change le hash
        assert compute_chunk_hash("A > B\n\nbody") != compute_chunk_hash("A\n\nbody")

    def test_different_content_different_hash(self) -> None:
        assert compute_chunk_hash("a") != compute_chunk_hash("b")
