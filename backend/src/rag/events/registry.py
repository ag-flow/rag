"""Registre des events applicatifs que rag peut émettre vers workflow.

Un `AppEvent` porte l'identité DÉTERMINISTE de l'occurrence (`event_id`, clé de
dédup côté workflow), son code catalogue (`{provider}.{name}.vN`), l'instant
tz-aware et les champs métier « à plat » (jamais de clé préfixée `_`, réservée
au système).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Espace de noms figé pour dériver un _eventId déterministe d'un id métier :
# le même id métier produit toujours le même UUID → dédup fiable au rejeu.
_EVENT_NAMESPACE = uuid.UUID("5f9b8e2a-1c3d-4e6f-8a0b-2d4c6e8f0a1b")

# Codes d'events rag (provider = 'rag' — préfixe des event_types côté workflow).
WORKSPACE_CREATED = "rag.workspace.created.v1"

# Tous les codes émissibles (sert de validation de la liste blanche).
KNOWN_EVENT_CODES: frozenset[str] = frozenset({WORKSPACE_CREATED})


@dataclass(frozen=True)
class AppEvent:
    """Un event applicatif prêt à être transformé en enveloppe."""

    event_code: str  # ex. "rag.workspace.created.v1"
    occurred_at: datetime  # DOIT être tz-aware
    subject: dict[str, Any]  # champs métier à plat
    dedup_key: str  # identité métier stable (→ _eventId déterministe)
    trace_id: str | None = field(default=None)

    def event_id(self) -> str:
        """UUID déterministe (uuid5) dérivé du couple (code, dedup_key)."""
        return str(uuid.uuid5(_EVENT_NAMESPACE, f"{self.event_code}:{self.dedup_key}"))


def workspace_created(
    *, name: str, label: str, slug: str, owner_id: str | None, occurred_at: datetime
) -> AppEvent:
    """Event `rag.workspace.created.v1` — un workspace vient d'être créé."""
    return AppEvent(
        event_code=WORKSPACE_CREATED,
        occurred_at=occurred_at,
        subject={"name": name, "label": label, "slug": slug, "owner_id": owner_id},
        dedup_key=slug,
    )
