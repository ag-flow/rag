"""`require_apikey_owner` — propagation OBO sur la surface REST.

Régression : le workspace créé via MCP est attribué à l'humain (OBO résolu par
le middleware MCP), mais le push REST se présentait au nom de la CLÉ, faute
d'OBO sur ce chemin — d'où un 401 `invalid_workspace_apikey` sur son propre
workspace. Les deux surfaces doivent produire le même `owner_id`.

Les en-têtes sont signés à l'instant courant : `require_apikey_owner` n'expose
pas de `now` injectable, la fenêtre anti-rejeu (300 s) est donc réelle ici.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from rag.auth.obo import sign_actor
from rag.auth.owner import principal_to_owner_id
from rag.auth.workspace_auth import require_apikey_owner

_API_KEY = "shared-key-EXAMPLE"
_ACTOR = "3f2a9c81-0000-4000-8000-000000000001"
_KEY_OWNER = "k" * 64
_HUMAN_EMAIL = "gael@yoops.org"

_VALID_KEY = {"owner_id": _KEY_OWNER, "scope": "read_write"}


class _Headers:
    """Mime `starlette.datastructures.Headers` : mapping + accès `.raw`."""

    def __init__(self, raw: list[tuple[bytes, bytes]]) -> None:
        self.raw = raw
        self._map = {name.decode().lower(): value.decode() for name, value in raw}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._map.get(key.lower(), default)


def _request(raw_headers: list[tuple[bytes, bytes]], pool) -> SimpleNamespace:
    return SimpleNamespace(
        headers=_Headers(raw_headers),
        app=SimpleNamespace(state=SimpleNamespace(pools=SimpleNamespace(config_pool=pool))),
    )


def _bearer() -> list[tuple[bytes, bytes]]:
    return [(b"authorization", f"Bearer {_API_KEY}".encode())]


def _obo_headers(signature: bytes | None = None) -> list[tuple[bytes, bytes]]:
    ts = int(time.time())
    sig = signature if signature is not None else sign_actor(_ACTOR, ts, _API_KEY).encode()
    return [
        *_bearer(),
        (b"x-portal-actor", _ACTOR.encode()),
        (b"x-portal-actor-timestamp", str(ts).encode()),
        (b"x-portal-actor-signature", sig),
    ]


def _pool(*, key_row: dict[str, str] | None, identity_email: str | None = None) -> MagicMock:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=key_row)
    pool.fetchval = AsyncMock(return_value=identity_email)
    return pool


@pytest.mark.asyncio
async def test_signed_identity_attributes_call_to_human() -> None:
    """Cœur de la régression : REST doit attribuer à l'humain, comme MCP."""
    pool = _pool(key_row=_VALID_KEY, identity_email=_HUMAN_EMAIL)

    ctx = await require_apikey_owner(_request(_obo_headers(), pool))  # type: ignore[arg-type]

    assert ctx.owner_id == principal_to_owner_id(_HUMAN_EMAIL)
    assert ctx.owner_id != _KEY_OWNER
    assert ctx.scope == "read_write"


@pytest.mark.asyncio
async def test_without_obo_headers_falls_back_to_key_owner() -> None:
    """Appel direct sans portail : l'identité de la clé reste la référence."""
    pool = _pool(key_row=_VALID_KEY)

    ctx = await require_apikey_owner(_request(_bearer(), pool))  # type: ignore[arg-type]

    assert ctx.owner_id == _KEY_OWNER
    assert ctx.scope == "read_write"
    pool.fetchval.assert_not_awaited()


@pytest.mark.asyncio
async def test_forged_signature_falls_back_without_raising() -> None:
    """Identité mal signée : ignorée en silence, jamais un 401 (fail-safe)."""
    pool = _pool(key_row=_VALID_KEY, identity_email=_HUMAN_EMAIL)

    ctx = await require_apikey_owner(_request(_obo_headers(b"0" * 64), pool))  # type: ignore[arg-type]

    assert ctx.owner_id == _KEY_OWNER


@pytest.mark.asyncio
async def test_unknown_identity_falls_back_to_key_owner() -> None:
    pool = _pool(key_row=_VALID_KEY, identity_email=None)

    ctx = await require_apikey_owner(_request(_obo_headers(), pool))  # type: ignore[arg-type]

    assert ctx.owner_id == _KEY_OWNER


@pytest.mark.asyncio
async def test_invalid_key_still_401_before_any_obo_lookup() -> None:
    """Une identité signée ne rattrape jamais une clé invalide."""
    pool = _pool(key_row=None, identity_email=_HUMAN_EMAIL)

    with pytest.raises(HTTPException) as exc:
        await require_apikey_owner(_request(_obo_headers(), pool))  # type: ignore[arg-type]

    assert exc.value.status_code == 401
    assert exc.value.detail == "invalid_apikey"
    pool.fetchval.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_bearer_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await require_apikey_owner(_request([], _pool(key_row=_VALID_KEY)))  # type: ignore[arg-type]

    assert exc.value.status_code == 401
    assert exc.value.detail == "missing_bearer_token"
