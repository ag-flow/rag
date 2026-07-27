from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.enrichments import PromptTemplateCreate


def _create(**over: object) -> PromptTemplateCreate:
    base: dict[str, object] = {
        "name": "ctx",
        "language": "markdown",
        "metadata_key": "context",
        "prompt": "Situe {chunk}",
    }
    return PromptTemplateCreate(**{**base, **over})  # type: ignore[arg-type]


class TestPromptTemplateAxes:
    def test_defaults_are_legacy_document_metadata(self) -> None:
        req = _create()
        assert (req.target, req.timing) == ("document", "post_index_metadata")

    def test_chunk_inline_supported(self) -> None:
        req = _create(target="chunk", timing="embedding_inline")
        assert req.target == "chunk"

    def test_region_targets_validated(self) -> None:
        req = _create(target="region:code_fence:mermaid", timing="embedding_inline")
        assert req.target == "region:code_fence:mermaid"
        _create(target="region:table", timing="embedding_inline")
        with pytest.raises(ValidationError, match="target inconnu"):
            _create(target="region:mermaid", timing="embedding_inline")

    def test_unsupported_combos_rejected(self) -> None:
        with pytest.raises(ValidationError, match="combinaison non supportée"):
            _create(target="chunk", timing="post_index_metadata")
        with pytest.raises(ValidationError, match="combinaison non supportée"):
            _create(target="document", timing="embedding_inline")

    def test_unknown_timing_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timing inconnu"):
            _create(target="chunk", timing="realtime")
