from __future__ import annotations

from rag.db.workspace_structured import ChildRow, _dedupe_children, plan_children


class TestPlanChildren:
    def test_all_new_when_base_empty(self) -> None:
        plan = plan_children(set(), ["a", "b", "c"])
        assert plan.new_hashes == ["a", "b", "c"]
        assert plan.kept_hashes == []
        assert plan.deleted_hashes == []

    def test_unchanged_kept_no_reembed(self) -> None:
        plan = plan_children({"a", "b"}, ["a", "b"])
        assert plan.new_hashes == []
        assert plan.kept_hashes == ["a", "b"]
        assert plan.deleted_hashes == []

    def test_partial_edit_only_touches_changed(self) -> None:
        # 'b' supprimé, 'c' ajouté, 'a' inchangé
        plan = plan_children({"a", "b"}, ["a", "c"])
        assert plan.new_hashes == ["c"]
        assert plan.kept_hashes == ["a"]
        assert sorted(plan.deleted_hashes) == ["b"]

    def test_boundary_shift_keeps_unmoved_chunks(self) -> None:
        # insertion en tête (nouveau 'x'), le reste glisse mais hashes identiques
        plan = plan_children({"a", "b", "c"}, ["x", "a", "b", "c"])
        assert plan.new_hashes == ["x"]
        assert sorted(plan.kept_hashes) == ["a", "b", "c"]
        assert plan.deleted_hashes == []

    def test_duplicate_hashes_in_doc_deduped(self) -> None:
        plan = plan_children(set(), ["a", "a", "b"])
        assert plan.new_hashes == ["a", "b"]


class TestDedupeChildren:
    def test_keeps_first_occurrence(self) -> None:
        children = [
            ChildRow(chunk_hash="h1", embed_text="x", parent_key="p", chunk_index=0),
            ChildRow(chunk_hash="h1", embed_text="x", parent_key="p", chunk_index=1),
            ChildRow(chunk_hash="h2", embed_text="y", parent_key="p", chunk_index=2),
        ]
        out = _dedupe_children(children)
        assert [c.chunk_hash for c in out] == ["h1", "h2"]
        assert out[0].chunk_index == 0
