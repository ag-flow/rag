"""Enveloppe Porte A + sérialisation/signature — octets EXACTS signés ET postés.

Piège central du contrat : sérialiser UNE SEULE FOIS, puis signer et poster ces
mêmes octets. Toute re-sérialisation (espace, ordre, ensure_ascii) entre les
deux = 401. La signature est un HMAC-SHA256 **hex nu** (sans préfixe `sha256=`).
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256
from typing import Any

from rag.events.registry import AppEvent

_SPEC_VERSION = "1.0"


def to_envelope(event: AppEvent, *, source_uri: str) -> dict[str, Any]:
    """Enveloppe PLATE : 5 champs système à la racine + champs métier à plat.

    `_eventId` est déterministe (dédup) ; `_occurredAt` doit être tz-aware
    (RFC 3339) sinon workflow renvoie 422. Les clés métier ne commencent jamais
    par `_` (réservé au système).
    """
    if event.occurred_at.tzinfo is None:
        raise ValueError("occurred_at doit être tz-aware (RFC 3339)")
    env: dict[str, Any] = {
        "_eventId": event.event_id(),
        "_eventCode": event.event_code,
        "_occurredAt": event.occurred_at.isoformat(),
        "_source": source_uri,
        "_specVersion": _SPEC_VERSION,
    }
    if event.trace_id:
        env["_traceId"] = event.trace_id
    for key, value in event.subject.items():
        if key.startswith("_"):
            raise ValueError(f"champ métier interdit (préfixe système) : {key!r}")
        env[key] = value
    return env


def serialize(envelope: dict[str, Any]) -> bytes:
    """Sérialisation STABLE, une seule fois — ces octets sont signés ET postés."""
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode()


def sign(secret: str, raw_body: bytes) -> str:
    """HMAC-SHA256 hex NU des octets bruts (valeur de `x-signature`)."""
    return hmac.new(secret.encode(), raw_body, sha256).hexdigest()
