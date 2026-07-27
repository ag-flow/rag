from __future__ import annotations

import re
import unicodedata

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(label: str) -> str:
    """Dérive un slug depuis un label saisi librement.

    Minuscules, accents translittérés, tout caractère non alphanumérique
    devient un tiret. Ex : « Docs internes (Ollama) » → `docs-internes-ollama`.
    Convention partagée par les endpoints de coffre et les stratégies de
    chunking — le slug est toujours calculé serveur, jamais saisi.
    """
    normalized = unicodedata.normalize("NFKD", label)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return _SLUG_STRIP_RE.sub("-", ascii_only).strip("-")
