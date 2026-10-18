"""Résolution de l'owner effectif d'un appel par clé API (OBO, contrat v6).

Point d'application unique partagé par les deux surfaces du service (MCP et
REST) : c'est l'asymétrie entre elles qui attribuait deux `owner_id` distincts
au même humain porteur de la même clé.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.auth.obo import sign_actor
from rag.auth.obo_resolver import (
    OboRequiredError,
    resolve_effective_owner_id,
    resolve_obo_for_body_keys,
)
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


class TestRequireObo:
    """Clé « OBO obligatoire » : le fail-safe devient un refus (fail closed)."""

    async def _resolve(
        self, pool: MagicMock, headers: list[tuple[bytes, bytes]], *, now: float = _NOW
    ) -> str:
        return await resolve_effective_owner_id(
            pool,
            headers,
            _SECRET,
            key_owner_id=_KEY_OWNER,
            surface="rest",
            require_obo=True,
            now=now,
        )

    @pytest.mark.asyncio
    async def test_require_obo_with_signed_known_identity_returns_human_owner(self) -> None:
        owner = await self._resolve(_pool(_HUMAN_EMAIL), _signed_headers())
        assert owner == principal_to_owner_id(_HUMAN_EMAIL)

    @pytest.mark.asyncio
    async def test_require_obo_without_headers_raises_absent(self) -> None:
        with pytest.raises(OboRequiredError) as exc:
            await self._resolve(_pool(_HUMAN_EMAIL), [(b"authorization", b"Bearer k")])
        assert exc.value.reason == "absent"

    @pytest.mark.asyncio
    async def test_require_obo_with_incomplete_headers_raises_incomplete(self) -> None:
        headers = [h for h in _signed_headers() if h[0] != b"x-portal-actor-timestamp"]
        with pytest.raises(OboRequiredError) as exc:
            await self._resolve(_pool(_HUMAN_EMAIL), headers)
        assert exc.value.reason == "incomplete_headers"

    @pytest.mark.asyncio
    async def test_require_obo_with_bad_signature_raises_invalid_signature(self) -> None:
        with pytest.raises(OboRequiredError) as exc:
            await self._resolve(_pool(_HUMAN_EMAIL), _signed_headers(secret="autre-cle"))
        assert exc.value.reason == "invalid_signature"

    @pytest.mark.asyncio
    async def test_require_obo_with_replayed_signature_raises_invalid_signature(self) -> None:
        with pytest.raises(OboRequiredError) as exc:
            await self._resolve(_pool(_HUMAN_EMAIL), _signed_headers(), now=float(_TS + 301))
        assert exc.value.reason == "invalid_signature"

    @pytest.mark.asyncio
    async def test_require_obo_with_unknown_identity_raises_unknown_identity(self) -> None:
        """Décision de cadrage : signature valide mais GUID inconnu → refus."""
        with pytest.raises(OboRequiredError) as exc:
            await self._resolve(_pool(None), _signed_headers())
        assert exc.value.reason == "unknown_identity"


class TestResolveOboForBodyKeys:
    """`/api/v1/search` : la clé voyage dans le corps, l'exigence OBO s'y applique."""

    @pytest.mark.asyncio
    async def test_key_without_flag_skips_obo_and_never_raises(self) -> None:
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=None)  # clé non marquée require_obo

        await resolve_obo_for_body_keys(pool, [], [_SECRET], surface="search")

        pool.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flagged_key_without_identity_raises(self) -> None:
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=_KEY_OWNER)

        with pytest.raises(OboRequiredError) as exc:
            await resolve_obo_for_body_keys(pool, [], [_SECRET], surface="search")
        assert exc.value.reason == "absent"

    @pytest.mark.asyncio
    async def test_flagged_key_with_identity_signed_by_another_key_raises(self) -> None:
        """Le secret de signature est LA clé du corps, pas une autre clé de l'appel."""
        pool = MagicMock()
        pool.fetchval = AsyncMock(side_effect=[_KEY_OWNER, _HUMAN_EMAIL])
        # Horodatage courant : seule la clé de signature doit faire échouer.
        ts = int(time.time())
        headers = [
            (b"x-portal-actor", _ACTOR.encode()),
            (b"x-portal-actor-timestamp", str(ts).encode()),
            (b"x-portal-actor-signature", sign_actor(_ACTOR, ts, "autre-cle").encode()),
        ]

        with pytest.raises(OboRequiredError) as exc:
            await resolve_obo_for_body_keys(pool, headers, [_SECRET], surface="search")
        assert exc.value.reason == "invalid_signature"

    @pytest.mark.asyncio
    async def test_duplicate_keys_are_checked_once(self) -> None:
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=None)

        await resolve_obo_for_body_keys(pool, [], [_SECRET, _SECRET], surface="search")

        pool.fetchval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flagged_key_with_its_own_signature_passes(self) -> None:
        pool = MagicMock()
        pool.fetchval = AsyncMock(side_effect=[_KEY_OWNER, _HUMAN_EMAIL])
        ts = int(time.time())
        headers = [
            (b"x-portal-actor", _ACTOR.encode()),
            (b"x-portal-actor-timestamp", str(ts).encode()),
            (b"x-portal-actor-signature", sign_actor(_ACTOR, ts, _SECRET).encode()),
        ]

        await resolve_obo_for_body_keys(pool, headers, [_SECRET], surface="search")
