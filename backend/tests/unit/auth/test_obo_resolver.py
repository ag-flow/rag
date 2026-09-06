"""Résolution de l'owner effectif d'un appel par clé API (OBO, contrat v6).

Point d'application unique partagé par les deux surfaces du service (MCP et
REST) : c'est l'asymétrie entre elles qui attribuait deux `owner_id` distincts
au même humain porteur de la même clé.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.auth.obo import sign_actor
from rag.auth.obo_resolver import resolve_effective_owner_id
from rag.auth.owner import principal_to_owner_id

_SECRET = "shared-key-EXAMPLE"
_ACTOR = "3f2a9c81-0000-4000-8000-000000000001"
_TS = 1763000000
_NOW = float(_TS + 10)
_KEY_OWNER = "k" * 64
_HUMAN_EMAIL = "gael@yoops.org"


def _signed_headers(secret: str = _SECRET) -> list[tuple[bytes, bytes]]:
    return [
        (b"authorization", b"Bearer k"),
        (b"x-portal-actor", _ACTOR.encode()),
        (b"x-portal-actor-timestamp", str(_TS).encode()),
        (b"x-portal-actor-signature", sign_actor(_ACTOR, _TS, secret).encode()),
    ]


def _pool(email: str | None) -> MagicMock:
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=email)
    return pool


class TestResolveEffectiveOwnerId:
    @pytest.mark.asyncio
    async def test_signed_identity_switches_to_human_owner(self) -> None:
        """Le cas nominal : l'attribution bascule sur l'EMAIL de l'humain."""
        owner = await resolve_effective_owner_id(
            _pool(_HUMAN_EMAIL),
            _signed_headers(),
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="rest",
            now=_NOW,
        )
        assert owner == principal_to_owner_id(_HUMAN_EMAIL)

    @pytest.mark.asyncio
    async def test_no_obo_headers_keeps_key_owner(self) -> None:
        owner = await resolve_effective_owner_id(
            _pool(_HUMAN_EMAIL),
            [(b"authorization", b"Bearer k")],
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="rest",
            now=_NOW,
        )
        assert owner == _KEY_OWNER

    @pytest.mark.asyncio
    async def test_invalid_signature_keeps_key_owner(self) -> None:
        """Signature forgée avec un autre secret → ignorée, jamais un 401."""
        owner = await resolve_effective_owner_id(
            _pool(_HUMAN_EMAIL),
            _signed_headers(secret="mauvaise-cle"),
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="rest",
            now=_NOW,
        )
        assert owner == _KEY_OWNER

    @pytest.mark.asyncio
    async def test_incomplete_headers_keep_key_owner(self) -> None:
        headers = [h for h in _signed_headers() if h[0] != b"x-portal-actor-signature"]
        owner = await resolve_effective_owner_id(
            _pool(_HUMAN_EMAIL),
            headers,
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="rest",
            now=_NOW,
        )
        assert owner == _KEY_OWNER

    @pytest.mark.asyncio
    async def test_unknown_identity_keeps_key_owner(self) -> None:
        """GUID signé mais absent de users.identity → fail-safe sur la clé."""
        owner = await resolve_effective_owner_id(
            _pool(None),
            _signed_headers(),
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="rest",
            now=_NOW,
        )
        assert owner == _KEY_OWNER

    @pytest.mark.asyncio
    async def test_identity_lookup_skipped_without_headers(self) -> None:
        """Aucun aller-retour base quand le portail ne propage rien."""
        pool = _pool(_HUMAN_EMAIL)
        await resolve_effective_owner_id(
            pool,
            [(b"authorization", b"Bearer k")],
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="mcp",
            now=_NOW,
        )
        pool.fetchval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_replayed_identity_outside_window_keeps_key_owner(self) -> None:
        """Hors fenêtre anti-rejeu (300 s) → identité ignorée."""
        owner = await resolve_effective_owner_id(
            _pool(_HUMAN_EMAIL),
            _signed_headers(),
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="rest",
            now=float(_TS + 301),
        )
        assert owner == _KEY_OWNER
