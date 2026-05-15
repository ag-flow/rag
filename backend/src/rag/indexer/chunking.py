from __future__ import annotations


def chunk_text(
    content: str,
    *,
    max_chars: int = 2000,
    min_chars: int = 200,
    overlap_chars: int = 200,
) -> list[str]:
    """Découpe `content` en chunks de ~max_chars, avec overlap entre chunks.

    Algorithme :
      1. Split sur `\\n\\n` (paragraphes) ; strip + retire vides.
      2. Coalesce paragraphes < min_chars avec le suivant tant que la
         concaténation reste ≤ max_chars.
      3. Split paragraphes > max_chars sur un séparateur naturel
         (`. `, `\\n`, ` `) cherché dans la fenêtre [max_chars - 200, max_chars] ;
         à défaut, coupe brutalement à max_chars.
      4. Ajoute overlap_chars chars en tête de chaque chunk (sauf le premier),
         pris en fin du précédent.

    Cas particuliers :
      - content vide ou whitespace-only → []
      - 1 paragraphe court → [content_stripped]
      - Code sans `\\n\\n` → fallback split sur `\\n`
      - overlap_chars >= max_chars → ValueError
    """
    if overlap_chars >= max_chars:
        raise ValueError(f"overlap_chars ({overlap_chars}) must be < max_chars ({max_chars})")

    stripped = content.strip()
    if not stripped:
        return []

    # 1. Split paragraphes
    paragraphs = [p.strip() for p in stripped.split("\n\n") if p.strip()]

    # Fallback : si pas de `\n\n`, split sur `\n` quand le bloc est trop grand.
    if len(paragraphs) == 1 and len(paragraphs[0]) > max_chars:
        paragraphs = [p for p in paragraphs[0].split("\n") if p.strip()]

    # 2. Coalesce les petits paragraphes
    coalesced: list[str] = []
    buffer = ""
    for p in paragraphs:
        if not buffer:
            buffer = p
            continue
        if len(buffer) < min_chars and len(buffer) + 2 + len(p) <= max_chars:
            buffer = f"{buffer}\n\n{p}"
        else:
            coalesced.append(buffer)
            buffer = p
    if buffer:
        coalesced.append(buffer)

    # 3. Split les gros paragraphes
    split_chunks: list[str] = []
    for p in coalesced:
        if len(p) <= max_chars:
            split_chunks.append(p)
            continue
        split_chunks.extend(_split_big_paragraph(p, max_chars))

    # 4. Ajout d'overlap
    if overlap_chars <= 0 or len(split_chunks) <= 1:
        return split_chunks

    overlapped: list[str] = [split_chunks[0]]
    for i in range(1, len(split_chunks)):
        prev_tail = split_chunks[i - 1][-overlap_chars:]
        overlapped.append(prev_tail + split_chunks[i])
    return overlapped


def _split_big_paragraph(p: str, max_chars: int) -> list[str]:
    """Split un paragraphe > max_chars sur un séparateur naturel."""
    chunks: list[str] = []
    remaining = p
    while len(remaining) > max_chars:
        # Cherche un séparateur dans [max_chars - 200, max_chars]
        window_start = max(0, max_chars - 200)
        window = remaining[window_start:max_chars]
        cut_pos = -1
        # Préférence : `. `, `\n`, ` `
        for sep in (". ", "\n", " "):
            idx = window.rfind(sep)
            if idx != -1:
                cut_pos = window_start + idx + len(sep)
                break
        if cut_pos == -1:
            cut_pos = max_chars  # coupe brutalement
        chunks.append(remaining[:cut_pos].strip())
        remaining = remaining[cut_pos:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
