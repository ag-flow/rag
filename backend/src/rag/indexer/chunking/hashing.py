from __future__ import annotations

from hashlib import sha256

_PREFIX = "sha256:"


def compute_chunk_hash(embed_text: str) -> str:
    """Hash d'identité d'un chunk = ``sha256:<hex>`` du texte EMBEDDÉ.

    Porte sur le texte exact envoyé au provider (breadcrumb inclus) : c'est
    l'ancre du dédoublonnage incrémental (ADR 0001 §5). Déterministe et
    idempotent — deux exécutions sur un contenu inchangé produisent le même
    hash, donc aucun ré-embed.
    """
    return _PREFIX + sha256(embed_text.encode("utf-8")).hexdigest()
