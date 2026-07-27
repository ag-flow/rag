"""Livraison HTTP d'une enveloppe signée vers workflow (Porte A) — pure, sans DB.

`deliver` signe les octets déjà sérialisés et POST `content=raw_body` (JAMAIS
`json=`, qui re-sérialiserait). Succès = HTTP 202 (neuf OU dédupliqué : un rejeu
est un succès idempotent). Tout autre code = échec de livraison.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from rag.events.envelope import serialize, sign, to_envelope
from rag.events.registry import AppEvent


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    status_code: int
    detail: str


def _endpoint(base_url: str, source_id: str) -> str:
    return f"{base_url.rstrip('/')}/events/{source_id}"


async def deliver(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    source_id: str,
    secret: str,
    raw_body: bytes,
) -> DeliveryResult:
    """Signe `raw_body` et le POST tel quel. 202 = succès (idempotent)."""
    signature = sign(secret, raw_body)
    try:
        resp = await client.post(
            _endpoint(base_url, source_id),
            content=raw_body,
            headers={"x-signature": signature, "content-type": "application/json"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        # Message SANS secret ni corps.
        return DeliveryResult(
            delivered=False, status_code=0, detail=f"transport: {type(exc).__name__}"
        )
    if resp.status_code == 202:
        return DeliveryResult(delivered=True, status_code=202, detail="accepted")
    return DeliveryResult(
        delivered=False, status_code=resp.status_code, detail=f"http {resp.status_code}"
    )


def build_test_envelope(source_uri: str) -> bytes:
    """Enveloppe de test `{app}.testevent.v1` (non cataloguée → acceptée non validée).

    Sert au test de connectivité de bout en bout SANS écrire dans les schémas
    réels ni dans l'outbox. `app` = dernier segment du source_uri."""
    app = source_uri.rstrip(":").rsplit(":", 1)[-1] or "rag"
    event = AppEvent(
        event_code=f"{app}.testevent.v1",
        occurred_at=datetime.now(UTC),
        subject={"ping": True},
        dedup_key="test-connection",
    )
    return serialize(to_envelope(event, source_uri=source_uri))
