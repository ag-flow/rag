from __future__ import annotations

from rag.indexer.chunking.protocol import Chunk


class ParagraphChunker:
    """Découpe un texte par paragraphes, avec coalesce des petits + split des gros + overlap.

    Encapsule l'algorithme historique de `chunk_text` (M4a). `metadata` reste vide.
    """

    def __init__(
        self,
        *,
        max_chars: int,
        min_chars: int,
        overlap_chars: int,
    ) -> None:
        self._max_chars = max_chars
        self._min_chars = min_chars
        self._overlap_chars = overlap_chars

    def chunk(self, content: str) -> list[Chunk]:
        """Découpe `content` en chunks paragraphe.

        Algorithme en 4 étapes :
        1. Split sur double-newline (fallback single-newline si un paragraphe
           unique dépasse `max_chars`).
        2. Coalesce des paragraphes courts (< `min_chars`) tant que la somme
           reste sous `max_chars`.
        3. Split des paragraphes trop gros sur frontière naturelle (". ", "\\n", " ").
        4. Préfixe chaque chunk (sauf le premier) par les `overlap_chars` derniers
           caractères du chunk précédent.

        Retourne `[]` si `content` est vide ou whitespace-only.
        Lève `ValueError` si `overlap_chars >= max_chars` (configuration invalide).
        """
        if self._overlap_chars >= self._max_chars:
            raise ValueError(
                f"overlap_chars ({self._overlap_chars}) must be < max_chars ({self._max_chars})"
            )

        stripped = content.strip()
        if not stripped:
            return []

        paragraphs = [p.strip() for p in stripped.split("\n\n") if p.strip()]
        if len(paragraphs) == 1 and len(paragraphs[0]) > self._max_chars:
            paragraphs = [p for p in paragraphs[0].split("\n") if p.strip()]

        coalesced: list[str] = []
        buffer = ""
        for p in paragraphs:
            if not buffer:
                buffer = p
                continue
            if len(buffer) < self._min_chars and len(buffer) + 2 + len(p) <= self._max_chars:
                buffer = f"{buffer}\n\n{p}"
            else:
                coalesced.append(buffer)
                buffer = p
        if buffer:
            coalesced.append(buffer)

        # Réserve le budget de l'overlap dans la taille de découpage pour que
        # les chunks finaux (préfixés par la queue du chunk précédent) ne
        # dépassent jamais max_chars (BUG-045).
        split_budget = self._max_chars
        if self._overlap_chars > 0 and len(coalesced) > 1:
            split_budget = self._max_chars - self._overlap_chars

        split_chunks: list[str] = []
        for p in coalesced:
            if len(p) <= split_budget:
                split_chunks.append(p)
                continue
            split_chunks.extend(self._split_big_paragraph(p, split_budget))

        if self._overlap_chars <= 0 or len(split_chunks) <= 1:
            return [Chunk(content=s) for s in split_chunks]

        result: list[Chunk] = [Chunk(content=split_chunks[0])]
        for i in range(1, len(split_chunks)):
            prev_tail = split_chunks[i - 1][-self._overlap_chars :]
            result.append(Chunk(content=prev_tail + split_chunks[i]))
        return result

    def _split_big_paragraph(self, p: str, max_chars: int | None = None) -> list[str]:
        budget = self._max_chars if max_chars is None else max_chars
        chunks: list[str] = []
        remaining = p
        while len(remaining) > budget:
            window_start = max(0, budget - 200)
            window = remaining[window_start:budget]
            cut_pos = -1
            for sep in (". ", "\n", " "):
                idx = window.rfind(sep)
                if idx != -1:
                    cut_pos = window_start + idx + len(sep)
                    break
            if cut_pos == -1:
                cut_pos = budget
            chunks.append(remaining[:cut_pos].strip())
            remaining = remaining[cut_pos:].lstrip()
        if remaining:
            chunks.append(remaining)
        return chunks
