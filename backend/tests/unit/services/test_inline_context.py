from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, DroppedRegion
from rag.services import inline_context
from rag.services.inline_context import apply_inline_context

_WS = uuid4()


class _FakeResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        return "sk-fake"


def _binding_row(template_id: UUID, *, target: str) -> dict[str, Any]:
    return {
        "template_id": template_id,
        "metadata_key": "context",
        "prompt": "Situe cet extrait : {chunk}",
        "prompt_version": 1,
        "target": target,
        "llm_provider": "ollama",
        "llm_model": "llama3",
        "api_key_ref": None,
        "llm_base_url": "http://fake",
    }


class _FakePool:
    """Bindings (fetch), cache (fetchval/execute) — le LLM est patché à part."""

    def __init__(self, bindings: list[dict[str, Any]]) -> None:
        self._bindings = bindings
        self.cache: dict[tuple, str] = {}
        self.inserts = 0

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        assert "embedding_inline" in query
        return self._bindings

    async def fetchval(self, query: str, *args: Any) -> str | None:
        return self.cache.get(args[1:4])

    async def execute(self, query: str, *args: Any) -> str:
        self.inserts += 1
        self.cache[args[1:4]] = args[4]
        return "INSERT 0 1"


def _doc() -> ChunkedDocument:
    return ChunkedDocument(
        parents=[],
        children=[
            ChildChunk(embed_text="Guide\n\nInstallez le paquet.", parent_key="Guide"),
            ChildChunk(embed_text="Guide\n\nLancez ensuite le service.", parent_key="Guide"),
        ],
        dropped_regions=[
            DroppedRegion(
                region_type="code_fence",
                qualifier="mermaid",
                content="graph TD; A-->B;",
                parent_key="Guide/Archi",
                crumb=("Guide", "Archi"),
                breadcrumb_depth=-1,
            )
        ],
    )


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> str:
        calls.append(kwargs)
        return f"[ctx {len(calls)}]"

    monkeypatch.setattr(inline_context, "call_llm_with_cached_prefix", _fake)
    return calls


@pytest.mark.asyncio
async def test_no_binding_returns_doc_unchanged(fake_llm: list) -> None:
    pool = _FakePool(bindings=[])
    doc = _doc()
    result = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=doc,
        resolver=_FakeResolver(),
    )
    assert result is doc  # bit-à-bit : aucun appel LLM, aucun objet recréé
    assert fake_llm == []


@pytest.mark.asyncio
async def test_chunk_target_prefixes_context_and_caches(fake_llm: list) -> None:
    pool = _FakePool(bindings=[_binding_row(uuid4(), target="chunk")])
    result = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide complet",
        doc=_doc(),
        resolver=_FakeResolver(),
    )
    contextualized = [c for c in result.children if c.metadata.get("inline_context")]
    assert len(contextualized) == 2
    assert all("\n\n" in c.embed_text for c in contextualized)
    assert len(fake_llm) == 2  # un appel par chunk…
    assert pool.inserts == 2  # …persisté pour l'idempotence
    # le document complet est passé en préfixe cachable
    assert fake_llm[0]["cached_prefix"] == "# Guide complet"


@pytest.mark.asyncio
async def test_cache_hit_skips_llm(fake_llm: list) -> None:
    binding = _binding_row(uuid4(), target="chunk")
    pool = _FakePool(bindings=[binding])
    doc = _doc()
    first = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=doc,
        resolver=_FakeResolver(),
    )
    calls_after_first = len(fake_llm)
    second = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=doc,
        resolver=_FakeResolver(),
    )
    assert len(fake_llm) == calls_after_first  # réindexation → zéro appel LLM
    # idempotence stricte : mêmes textes embeddés → mêmes hashes → diff vide
    assert [c.embed_text for c in first.children] == [c.embed_text for c in second.children]


@pytest.mark.asyncio
async def test_region_target_embeds_description_of_dropped_region(fake_llm: list) -> None:
    pool = _FakePool(bindings=[_binding_row(uuid4(), target="region:code_fence:mermaid")])
    result = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=_doc(),
        resolver=_FakeResolver(),
    )
    synthetic = [c for c in result.children if c.metadata.get("region_type") == "code_fence"]
    assert len(synthetic) == 1
    chunk = synthetic[0]
    assert chunk.parent_key == "Guide/Archi"
    assert "graph TD" not in chunk.embed_text  # description, pas la source
    assert "[ctx 1]" in chunk.embed_text
    assert chunk.embed_text.startswith("Guide")  # breadcrumb préfixé
    # les chunks d'origine sont intacts
    assert len(result.children) == 3


@pytest.mark.asyncio
async def test_region_target_qualifier_mismatch_is_noop(fake_llm: list) -> None:
    pool = _FakePool(bindings=[_binding_row(uuid4(), target="region:code_fence:python")])
    result = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=_doc(),
        resolver=_FakeResolver(),
    )
    assert len(result.children) == 2
    assert fake_llm == []
