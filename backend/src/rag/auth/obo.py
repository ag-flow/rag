"""OBO — identité humaine signée propagée par le portail vers le service MCP.

Contrat figé (globals/documentation d0e2dad3, interop byte-for-byte). Le portail
ajoute trois en-têtes signés HMAC quand `forward_identity` est activé pour le
backend rag :

    x-portal-actor            = owner_login (principal humain)
    x-portal-actor-timestamp  = instant d'émission, unix secondes
    x-portal-actor-signature  = HMAC-SHA256 hex de f"{actor}\\n{timestamp}"

Le secret de signature est **la clé API présentée sur la MÊME requête** (le
Bearer que rag valide déjà) — rien à provisionner. Frontière de confiance :
une identité non signée / mal signée est IGNORÉE (on retombe sur l'identité de
la clé), jamais un 401. Un acteur venu du corps d'un tool n'est jamais une
source d'identité.
"""

from __future__ import annotations

import hmac
import time
from hashlib import sha256

ACTOR_HEADER = b"x-portal-actor"
TIMESTAMP_HEADER = b"x-portal-actor-timestamp"
SIGNATURE_HEADER = b"x-portal-actor-signature"

_WINDOW_SECONDS = 300


def sign_actor(actor: str, timestamp: int, secret: str) -> str:
    """Signature HMAC-SHA256 hex de la charge canonique (miroir de portal/mcp/obo.py)."""
    payload = f"{actor}\n{timestamp}".encode()
    return hmac.new(secret.encode(), payload, sha256).hexdigest()


def verify_actor(
    actor: str,
    timestamp: str,
    signature: str,
    api_key: str,
    *,
    window: int = _WINDOW_SECONDS,
    now: float | None = None,
) -> bool:
    """Vérifie la signature (temps constant) et la fenêtre anti-rejeu (300 s)."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > window:
        return False
    expected = sign_actor(actor, ts, api_key)
    return hmac.compare_digest(expected, signature)


def read_obo_actor(
    headers: list[tuple[bytes, bytes]],
    api_key: str,
    *,
    now: float | None = None,
) -> str | None:
    """Login acteur SI les trois en-têtes signés sont valides, sinon None.

    Jamais d'exception, jamais de 401 : en-tête absent/mal signé → None (retour
    à l'identité de la clé). C'est la garde de confiance du contrat OBO.
    """
    lowered = {name.lower(): value for name, value in headers}
    actor = lowered.get(ACTOR_HEADER)
    timestamp = lowered.get(TIMESTAMP_HEADER)
    signature = lowered.get(SIGNATURE_HEADER)
    if actor is None or timestamp is None or signature is None:
        return None
    actor_str = actor.decode(errors="replace")
    if verify_actor(actor_str, timestamp.decode(), signature.decode(), api_key, now=now):
        return actor_str
    return None
