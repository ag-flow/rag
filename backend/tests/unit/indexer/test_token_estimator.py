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

    def test_cjk_counted_one_token_per_char(self) -> None:
        # BUG-041 : le CJK ne doit pas être sous-estimé au ratio latin
        est = HeuristicTokenEstimator(char_ratio=4.0)
        assert est.estimate("中" * 10) == 10

    def test_mixed_cjk_and_latin(self) -> None:
        est = HeuristicTokenEstimator(char_ratio=4.0)
        # 8 chars latins -> 2 tokens ; 3 idéogrammes -> 3 tokens
        assert est.estimate("a" * 8 + "中文字") == 2 + 3

    def test_ascii_behavior_unchanged(self) -> None:
        # Aucune régression EN/FR : é/à sont « Ambiguous », traités comme du latin
        est = HeuristicTokenEstimator(char_ratio=4.0)
        assert est.estimate("café à Noël") == est.estimate("x" * len("café à Noël"))

    def test_emoji_not_underestimated(self) -> None:
        est = HeuristicTokenEstimator(char_ratio=4.0)
        assert est.estimate("😀" * 5) >= 5
