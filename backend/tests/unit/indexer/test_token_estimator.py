from __future__ import annotations

import pytest

from rag.indexer.chunking.tokens import HeuristicTokenEstimator


class TestHeuristicTokenEstimator:
    def test_empty_string_is_zero_tokens(self) -> None:
        est = HeuristicTokenEstimator(char_ratio=4.0)
        assert est.estimate("") == 0

    def test_estimate_is_ceil_of_len_over_ratio(self) -> None:
        est = HeuristicTokenEstimator(char_ratio=4.0)
        # 10 chars / 4 = 2.5 -> ceil -> 3
        assert est.estimate("a" * 10) == 3
        # 8 chars / 4 = 2 -> 2
        assert est.estimate("a" * 8) == 2
        # 1 char / 4 = 0.25 -> ceil -> 1 (jamais 0 pour du contenu non vide)
        assert est.estimate("a") == 1

    def test_ratio_changes_estimate(self) -> None:
        est = HeuristicTokenEstimator(char_ratio=2.0)
        assert est.estimate("a" * 10) == 5

    def test_deterministic(self) -> None:
        est = HeuristicTokenEstimator(char_ratio=4.0)
        text = "Lorem ipsum dolor sit amet, consectetur."
        assert est.estimate(text) == est.estimate(text)

    def test_rejects_non_positive_ratio(self) -> None:
        with pytest.raises(ValueError, match="char_ratio"):
            HeuristicTokenEstimator(char_ratio=0.0)
        with pytest.raises(ValueError, match="char_ratio"):
            HeuristicTokenEstimator(char_ratio=-1.0)
