from __future__ import annotations

import json

from rag.indexer.chunking import MarkdownChunker


def _default(heading_levels: tuple[int, ...] = (1, 2)) -> MarkdownChunker:
    return MarkdownChunker(
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        heading_levels=heading_levels,
    )


# ─── Cas de base ─────────────────────────────────────────────────────────────


def test_empty_returns_empty() -> None:
    assert _default().chunk("") == []


def test_no_heading_falls_back_to_paragraph() -> None:
    """Texte sans `#` → délègue à ParagraphChunker. Metadata = valeur neutre."""
    content = "Just plain text.\n\nAnother paragraph."
    result = _default().chunk(content)
    assert len(result) == 1
    assert result[0].metadata == {
        "section_title": None,
        "section_path": [],
        "heading_level": 0,
    }


def test_single_h1_section_returns_one_chunk() -> None:
    content = "# Title\n\nContent of the section."
    result = _default().chunk(content)
    assert len(result) == 1
    chunk = result[0]
    assert chunk.metadata == {
        "section_title": "Title",
        "section_path": [],
        "heading_level": 1,
    }
    assert "Title" in chunk.content
    assert "Content of the section" in chunk.content


def test_h1_h2_split_with_default_heading_levels() -> None:
    """# A\\n## B\\n## C → 3 chunks distincts."""
    content = "# A\n\nAlpha content.\n\n## B\n\nBravo content.\n\n## C\n\nCharlie content."
    result = _default().chunk(content)
    assert len(result) == 3
    titles = [c.metadata["section_title"] for c in result]
    assert titles == ["A", "B", "C"]
    levels = [c.metadata["heading_level"] for c in result]
    assert levels == [1, 2, 2]


# ─── Breadcrumb ──────────────────────────────────────────────────────────────


def test_section_path_captures_parent_headings_inside_levels() -> None:
    content = "# Doc\n\nIntro.\n\n## Install\n\nInstall details."
    result = _default(heading_levels=(1, 2)).chunk(content)
    install = next(c for c in result if c.metadata["section_title"] == "Install")
    assert install.metadata["section_path"] == ["Doc"]


def test_section_path_captures_parents_outside_levels() -> None:
    """H3 enrichit le breadcrumb même s'il ne déclenche pas de split."""
    content = "# Doc\n\nIntro.\n\n## Install\n\nTop install.\n\n### Linux\n\nLinux content."
    result = _default(heading_levels=(1, 2)).chunk(content)
    install = next(c for c in result if c.metadata["section_title"] == "Install")
    assert install.metadata["section_path"] == ["Doc"]
    assert "Linux" in install.content


def test_preamble_text_before_first_heading() -> None:
    content = "Intro freely written.\n\n# Doc\n\nDoc content."
    result = _default().chunk(content)
    assert len(result) == 2
    preamble = result[0]
    assert preamble.metadata == {
        "section_title": None,
        "section_path": [],
        "heading_level": 0,
    }
    assert "Intro freely written" in preamble.content


# ─── Sub-split de section longue ────────────────────────────────────────────


def test_long_section_subsplit_preserves_metadata() -> None:
    big_para = "Paragraph content. " * 200
    content = f"# Big\n\n{big_para}"
    result = _default().chunk(content)
    assert len(result) >= 2
    for chunk in result:
        assert chunk.metadata["section_title"] == "Big"
        assert chunk.metadata["heading_level"] == 1


def test_subsplit_does_not_cut_inside_fence() -> None:
    big_intro = "Intro text. " * 100
    fence = "```python\n" + "x = 1\n" * 100 + "```"
    content = f"# Section\n\n{big_intro}\n\n{fence}\n\nMore text."
    result = _default().chunk(content)
    found_fence_chunk = False
    for chunk in result:
        if "```python" in chunk.content:
            assert "```" in chunk.content[chunk.content.index("```python") + 9 :], (
                f"fence non terminé dans chunk: {chunk.content[:200]}..."
            )
            found_fence_chunk = True
    assert found_fence_chunk, "aucun chunk ne contient le fence"


def test_giant_fence_exceeds_max_chars_kept_intact() -> None:
    giant_fence = "```\n" + "y = 2\n" * 500 + "```"
    content = f"# Huge\n\nIntro.\n\n{giant_fence}"
    result = _default().chunk(content)
    fence_chunks = [c for c in result if "```" in c.content and c.content.count("```") >= 2]
    assert len(fence_chunks) >= 1


# ─── Configuration heading_levels ───────────────────────────────────────────


def test_heading_levels_only_h1_groups_subsections() -> None:
    content = "# A\n\nAlpha.\n\n## a1\n\nOne.\n\n## a2\n\nTwo."
    result = _default(heading_levels=(1,)).chunk(content)
    assert len(result) == 1
    assert result[0].metadata["section_title"] == "A"
    assert "a1" in result[0].content
    assert "a2" in result[0].content


def test_heading_levels_h1_h2_h3() -> None:
    content = "# Doc\n\nIntro.\n\n## Install\n\nTop.\n\n### From source\n\nDetails."
    result = _default(heading_levels=(1, 2, 3)).chunk(content)
    titles = [c.metadata["section_title"] for c in result]
    assert "From source" in titles
    from_source = next(c for c in result if c.metadata["section_title"] == "From source")
    assert from_source.metadata["section_path"] == ["Doc", "Install"]
    assert from_source.metadata["heading_level"] == 3


def test_heading_levels_h3_only() -> None:
    content = "# Top\n\nTop content.\n\n### Sub\n\nSub content."
    result = _default(heading_levels=(3,)).chunk(content)
    assert len(result) >= 1
    sub_chunks = [c for c in result if c.metadata.get("section_title") == "Sub"]
    assert len(sub_chunks) == 1
    assert sub_chunks[0].metadata["section_path"] == ["Top"]


# ─── Contrats metadata ──────────────────────────────────────────────────────


def test_metadata_keys_exact_set() -> None:
    content = "Preamble.\n\n# A\n\nText.\n\n## B\n\nMore."
    result = _default().chunk(content)
    expected_keys = {"section_title", "section_path", "heading_level"}
    for chunk in result:
        assert set(chunk.metadata.keys()) == expected_keys, (
            f"keys mismatch: {set(chunk.metadata.keys())} != {expected_keys}"
        )


def test_metadata_json_serializable() -> None:
    content = "# Title\n\nContent."
    result = _default().chunk(content)
    for chunk in result:
        json.dumps(dict(chunk.metadata))


# ─── Robustesse Markdown malformé ───────────────────────────────────────────


def test_unclosed_fence_does_not_crash() -> None:
    content = "# Title\n\n```python\nx = 1\n# pas de fermeture"
    result = _default().chunk(content)
    assert len(result) >= 1
    assert result[0].metadata["section_title"] == "Title"


def test_setext_heading_supported() -> None:
    content = "Title\n=====\n\nContent."
    result = _default().chunk(content)
    titles = [c.metadata.get("section_title") for c in result]
    assert "Title" in titles


def test_preamble_with_duplicated_heading_line_inside_fence() -> None:
    """Régression : un préambule contenant une ligne textuellement identique
    au heading déclenchant ne doit PAS être tronqué.

    Reproduit le bug détecté en review M9c-T3 : `_find_preamble_lines` cherchait
    le 1er match string, donc tombait sur la ligne dans le fence au lieu du
    vrai heading.
    """
    content = "```\n# Section\n```\n\n# Section\n\nReal content."
    result = _default().chunk(content)
    # Préambule : doit contenir l'intégralité du fence (```, # Section, ```)
    preamble = next(
        (c for c in result if c.metadata["section_title"] is None),
        None,
    )
    assert preamble is not None, "préambule non détecté"
    assert "```" in preamble.content, "fence ouvrant perdu"
    assert preamble.content.count("```") >= 2, "fence non préservée"
    assert "# Section" in preamble.content
