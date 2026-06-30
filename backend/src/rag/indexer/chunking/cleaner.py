from __future__ import annotations

import re
import unicodedata

from rag.indexer.chunking.structured import ChunkedDocument, StructuredChunkerProtocol


def clean_content_text(text: str) -> str:
    """Nettoyage non-destructif du texte avant chunking.

    Opérations (dans l'ordre) :
    1. Normalisation unicode NFKC — ligatures, espaces spéciaux, apostrophes
    2. CRLF / CR → LF
    3. Suppression des espaces et tabulations en fin de ligne
    4. Maximum 2 lignes vides consécutives

    L'indentation (espaces en début de ligne) est intégralement préservée —
    elle est sémantique pour le code Python/YAML/… Pas de normalisation des
    espaces en milieu de ligne (idem).
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


class CleaningChunkerWrapper:
    """Applique `clean_content_text` sur le contenu avant de déléguer au chunker interne.

    Implémente `StructuredChunkerProtocol`. Activé quand le param de stratégie
    `clean_content=true` est positionné dans `chunking_strategies.params` — le
    comportement est transparent quand le param est absent ou false.
    """

    def __init__(self, inner: StructuredChunkerProtocol) -> None:
        self._inner = inner

    def chunk(self, content: str) -> ChunkedDocument:
        return self._inner.chunk(clean_content_text(content))
