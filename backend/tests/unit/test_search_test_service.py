"""Banc de test de recherche (feature 1a9b8b67) : métriques par provenance et
campagne — verdict arithmétique, sans DB (pool et recherche factices)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from rag.services.search_test import (
    aggregate_metrics,
    first_relevant_rank,
    run_campaign,
)

_WS = uuid4()


class TestMetrics:
    def test_first_relevant_rank_matches_fragment(self) -> None:
        paths = ["a/x.md", "ragflow/{event.blockSlug}/7a753653-doc", "b.md"]
        assert first_relevant_rank(paths, "7a753653") == 2
        assert first_relevant_rank(paths, "absent") is None

    def test_aggregate_global_and_per_family(self) -> None:
        entries = [("litterale", 1), ("litterale", None), ("indirecte", 4)]
        m = aggregate_metrics(entries)
        assert m["recall@1"] == round(1 / 3, 4)
        assert m["recall@5"] == round(2 / 3, 4)
        assert m["mrr"] == round((1 + 0.25) / 3, 4)
        assert m["families"]["litterale"]["recall@1"] == 0.5
        assert m["families"]["indirecte"]["recall@5"] == 1.0


def _question(question: str, fragment: str, family: str = "litterale") -> dict[str, Any]:
    return {
        "id": uuid4(),
        "question": question,
        "expected_path_contains": fragment,
        "family": family,
        "enabled": True,
        "created_at": datetime(2026, 7, 27, tzinfo=UTC),
    }


def _fake_pool(questions: list[dict[str, Any]]) -> SimpleNamespace:
    conn = SimpleNamespace(
        fetchrow=AsyncMock(
            return_value={"id": uuid4(), "started_at": datetime(2026, 7, 27, tzinfo=UTC)}
        ),
        execute=AsyncMock(),
    )

    class _CM:
        async def __aenter__(self) -> Any:
            return conn

        async def __aexit__(self, *args: Any) -> bool:
            return False

    conn.transaction = lambda: _CM()
    pool = SimpleNamespace(
        fetch=AsyncMock(return_value=questions),
        acquire=lambda: _CM(),
        _conn=conn,
    )
    return pool


class TestRunCampaign:
    @pytest.mark.asyncio
    async def test_ranks_metrics_and_persistence(self) -> None:
        pool = _fake_pool(
            [
                _question("q1", "doc-aaa", "litterale"),
                _question("q2", "doc-bbb", "indirecte"),
            ]
        )

        async def search_fn(question: str) -> list[str]:
            return ["x/doc-aaa"] if question == "q1" else ["autre", "encore"]

        run = await run_campaign(
            pool, workspace_id=_WS, search_fn=search_fn, config={"hybrid": False}
        )

        assert run["questions_total"] == 2
        assert run["questions_failed"] == 1
        assert run["metrics"]["recall@1"] == 0.5
        assert run["results"][0]["rank"] == 1
        assert run["results"][1]["rank"] is None
        # Persistance : 1 INSERT run (fetchrow) + 1 INSERT par résultat.
        pool._conn.fetchrow.assert_awaited_once()
        assert pool._conn.execute.await_count == 2
        config_json = json.loads(pool._conn.fetchrow.await_args.args[2])
        assert config_json == {"hybrid": False, "top_k": 10}

    @pytest.mark.asyncio
    async def test_search_error_counts_as_miss(self) -> None:
        pool = _fake_pool([_question("q1", "doc-aaa")])

        async def search_fn(question: str) -> list[str]:
            raise RuntimeError("provider down")

        run = await run_campaign(pool, workspace_id=_WS, search_fn=search_fn, config={})
        assert run["questions_failed"] == 1
        assert run["results"][0]["rank"] is None

    @pytest.mark.asyncio
    async def test_no_enabled_question_raises(self) -> None:
        disabled = _question("q1", "doc-aaa")
        disabled["enabled"] = False
        pool = _fake_pool([disabled])

        async def search_fn(question: str) -> list[str]:  # pragma: no cover
            return []

        with pytest.raises(ValueError, match="aucune question"):
            await run_campaign(pool, workspace_id=_WS, search_fn=search_fn, config={})

    @pytest.mark.asyncio
    async def test_rank_beyond_top_k_is_a_miss(self) -> None:
        pool = _fake_pool([_question("q1", "doc-aaa")])

        async def search_fn(question: str) -> list[str]:
            return [f"p{i}" for i in range(10)] + ["x/doc-aaa"]  # rang 11 > top_k

        run = await run_campaign(pool, workspace_id=_WS, search_fn=search_fn, config={}, top_k=10)
        assert run["results"][0]["rank"] is None
