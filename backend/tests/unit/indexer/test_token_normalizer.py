from __future__ import annotations

import pytest

from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.normalizer import TokenBounds, TokenNormalizer
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

# ratio=1.0 → 1 token == 1 caractère, math déterministe dans les tests.
_EST = HeuristicTokenEstimator(char_ratio=1.0)


def _norm(*, target: int, floor: int, overlap: int, hard: int) -> TokenNormalizer:
    return TokenNormalizer(
        _EST,
        TokenBounds(
            child_target_tokens=target,
            floor_tokens=floor,
            overlap_tokens=overlap,
            hard_ceiling_tokens=hard,
        ),
    )


class TestValidation:
    def test_floor_gt_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="floor"):
            _norm(target=10, floor=11, overlap=2, hard=20)

    def test_overlap_ge_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            _norm(target=10, floor=2, overlap=10, hard=20)

    def test_target_gt_hard_ceiling_rejected(self) -> None:
        with pytest.raises(ValueError, match="hard_ceiling"):
            _norm(target=30, floor=2, overlap=2, hard=20)

    def test_non_positive_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="child_target"):
            _norm(target=0, floor=0, overlap=0, hard=20)

    def test_negative_values_rejected(self) -> None:
        with pytest.raises(ValueError):
            _norm(target=10, floor=-1, overlap=2, hard=20)
        with pytest.raises(ValueError):
            _norm(target=10, floor=2, overlap=-1, hard=20)


class TestEmpty:
    def test_empty_list(self) -> None:
        assert _norm(target=10, floor=2, overlap=2, hard=20).normalize([]) == []

    def test_blank_blocks_dropped(self) -> None:
        assert _norm(target=10, floor=2, overlap=2, hard=20).normalize(["  ", "", "\n"]) == []


class TestFloorMerge:
    def test_small_adjacent_blocks_merged_up(self) -> None:
        n = _norm(target=12, floor=4, overlap=2, hard=30)
        out = n.normalize(["aaa", "bb", "ccccccccc"])  # 3, 2, 9
        # "aaa"(3<floor) + "bb" => "aaa\n\nbb" (7) ; puis bloc de 9 séparé
        assert out == ["aaa\n\nbb", "ccccccccc"]

    def test_no_merge_when_would_exceed_target(self) -> None:
        n = _norm(target=8, floor=6, overlap=2, hard=30)
        out = n.normalize(["aaaaa", "bbbbb"])  # 5 + 5, merge ferait 12 > 8
        assert out == ["aaaaa", "bbbbb"]

    def test_block_at_or_above_floor_not_merged(self) -> None:
        n = _norm(target=20, floor=3, overlap=2, hard=30)
        out = n.normalize(["aaaa", "bbbb"])  # 4 >= floor 3 → pas de merge
        assert out == ["aaaa", "bbbb"]


class TestCeilingSplit:
    def test_oversized_block_split_into_pieces_within_target(self) -> None:
        n = _norm(target=12, floor=2, overlap=2, hard=30)
        out = n.normalize(["aaaa bbbb cccc dddd eeee"])  # 24 chars
        assert len(out) == 3
        # cœurs attendus (overlap mis à part)
        assert out[0] == "aaaa bbbb"
        assert out[1].startswith("bb ")  # overlap de 2 tokens depuis la pièce précédente
        assert out[2].startswith("dd ")
        for piece in out:
            assert _EST.estimate(piece) <= 30

    def test_indivisible_unit_over_target_but_under_hard_emitted_whole(self) -> None:
        n = _norm(target=12, floor=2, overlap=2, hard=30)
        out = n.normalize(["ccccccccccccc"])  # 13 > target 12, <= hard 30, insécable
        assert out == ["ccccccccccccc"]

    def test_no_overlap_when_overlap_zero(self) -> None:
        n = _norm(target=12, floor=2, overlap=0, hard=30)
        out = n.normalize(["aaaa bbbb cccc dddd eeee"])
        # même groupage que le cas avec overlap, mais sans préfixe de recouvrement
        assert out == ["aaaa bbbb", "cccc dddd", "eeee"]


class TestHardGuard:
    def test_indivisible_unit_over_hard_ceiling_raises(self) -> None:
        n = _norm(target=4, floor=1, overlap=1, hard=5)
        with pytest.raises(ChunkTooLargeError, match="6"):
            n.normalize(["aaaaaa"])  # 6 > hard 5, insécable
