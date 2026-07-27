from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, RoutedRegion
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
        if "workspace_extension_triggers" in query:
            # Résolution du trigger par pattern (trigger_match) : un trigger
            # générique matche dès qu'il y a des bindings à servir.
            if not self._bindings:
                return []
            return [{"id": uuid4(), "pattern": "**/*.md", "strategy_id": None}]
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
        routed_regions=[
            RoutedRegion(
                region_type="code_fence",
                qualifier="mermaid",
                content="graph TD; A-->B;",
                parent_key="Guide/Archi",
                crumb=("Guide", "Archi"),
                breadcrumb_depth=-1,
                source_embedded=False,
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


@pytest.mark.asyncio
async def test_llm_failure_indexes_chunk_without_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Politique S6.2 : échec LLM → chunk indexé SANS contexte + warning,
    jamais d'échec du job complet."""

    async def _boom(**kwargs: Any) -> str:
        raise RuntimeError("provider down")

    monkeypatch.setattr(inline_context, "call_llm_with_cached_prefix", _boom)
    pool = _FakePool(bindings=[_binding_row(uuid4(), target="chunk")])
    doc = _doc()
    result = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=doc,
        resolver=_FakeResolver(),
    )
    # aucun contexte injecté, mais les chunks d'origine sont bien là
    assert [c.embed_text for c in result.children] == [c.embed_text for c in doc.children]
    assert pool.inserts == 0  # rien de mis en cache sur échec


@pytest.mark.asyncio
async def test_region_binding_specificity_exact_beats_generic(fake_llm: list) -> None:
    """S6.3 : `region:type:qualifier` exact > `region:type` — UNE description."""
    exact = _binding_row(uuid4(), target="region:code_fence:mermaid")
    exact["metadata_key"] = "exact"
    generic = _binding_row(uuid4(), target="region:code_fence")
    generic["metadata_key"] = "generic"
    pool = _FakePool(bindings=[generic, exact])  # le générique arrive en premier
    result = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=_doc(),
        resolver=_FakeResolver(),
    )
    synthetic = [c for c in result.children if c.metadata.get("region_type")]
    assert len(synthetic) == 1  # une seule description malgré deux bindings
    assert synthetic[0].metadata["inline_context"] == "exact"


@pytest.mark.asyncio
async def test_source_embedded_region_gets_additive_description(fake_llm: list) -> None:
    """S6.3 : politique non parent_only → le source EST embeddé et la
    description s'AJOUTE (chunk synthétique en plus)."""
    doc = ChunkedDocument(
        parents=[],
        children=[ChildChunk(embed_text="T\n\n```python\nprint(1)\n```", parent_key="T")],
        routed_regions=[
            RoutedRegion(
                region_type="code_fence",
                qualifier="python",
                content="print(1)",
                parent_key="T",
                crumb=("T",),
                breadcrumb_depth=-1,
                source_embedded=True,  # route atomique keep_whole
            )
        ],
    )
    pool = _FakePool(bindings=[_binding_row(uuid4(), target="region:code_fence")])
    result = await apply_inline_context(
        pool,  # type: ignore[arg-type]
        workspace_id=_WS,
        path="guide.md",
        content="# Guide",
        doc=doc,
        resolver=_FakeResolver(),
    )
    assert len(result.children) == 2  # source intact + description additive
    assert "print(1)" in result.children[0].embed_text
    described = result.children[1]
    assert described.metadata["region_source_embedded"] is True
    assert "[ctx 1]" in described.embed_text
