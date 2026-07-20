"""OBO — vérification de l'identité humaine signée (contrat figé d0e2dad3)."""

from __future__ import annotations

from rag.auth.obo import read_obo_actor, sign_actor, verify_actor

# Vecteur d'interop byte-for-byte du contrat portail.
_SECRET = "shared-key-EXAMPLE"
_ACTOR = "gael"
_TS = 1763000000
_SIG = "6c1a34eb1b1ca3d9be66ea366460a397e5a684fa647f302368cc7237e8ec93ae"
# `now` figé dans la fenêtre du timestamp d'interop.
_NOW = float(_TS + 10)


class TestSignActorVector:
    def test_signature_matches_interop_vector(self) -> None:
        assert sign_actor(_ACTOR, _TS, _SECRET) == _SIG


class TestVerifyActor:
    def test_valid_vector_accepted(self) -> None:
        assert verify_actor(_ACTOR, str(_TS), _SIG, _SECRET, now=_NOW) is True

    def test_tampered_signature_rejected(self) -> None:
        assert verify_actor(_ACTOR, str(_TS), "0" * 64, _SECRET, now=_NOW) is False

    def test_tampered_actor_rejected(self) -> None:
        assert verify_actor("mallory", str(_TS), _SIG, _SECRET, now=_NOW) is False

    def test_wrong_secret_rejected(self) -> None:
        assert verify_actor(_ACTOR, str(_TS), _SIG, "autre-cle", now=_NOW) is False

    def test_out_of_window_rejected(self) -> None:
        # 301 s après l'émission → hors fenêtre anti-rejeu (300 s).
        assert verify_actor(_ACTOR, str(_TS), _SIG, _SECRET, now=float(_TS + 301)) is False

    def test_non_integer_timestamp_rejected(self) -> None:
        assert verify_actor(_ACTOR, "pas-un-entier", _SIG, _SECRET, now=_NOW) is False


def _headers(actor: str, ts: str, sig: str) -> list[tuple[bytes, bytes]]:
    return [
        (b"authorization", b"Bearer k"),
        (b"x-portal-actor", actor.encode()),
        (b"x-portal-actor-timestamp", ts.encode()),
        (b"x-portal-actor-signature", sig.encode()),
    ]


class TestReadOboActor:
    def test_valid_headers_return_actor(self) -> None:
        headers = _headers(_ACTOR, str(_TS), _SIG)
        assert read_obo_actor(headers, _SECRET, now=_NOW) == _ACTOR

    def test_case_insensitive_headers(self) -> None:
        headers = [
            (b"X-Portal-Actor", _ACTOR.encode()),
            (b"X-Portal-Actor-Timestamp", str(_TS).encode()),
            (b"X-Portal-Actor-Signature", _SIG.encode()),
        ]
        assert read_obo_actor(headers, _SECRET, now=_NOW) == _ACTOR

    def test_missing_headers_return_none(self) -> None:
        assert read_obo_actor([(b"authorization", b"Bearer k")], _SECRET, now=_NOW) is None

    def test_forged_signature_ignored_not_raised(self) -> None:
        headers = _headers(_ACTOR, str(_TS), "deadbeef" * 8)
        assert read_obo_actor(headers, _SECRET, now=_NOW) is None


class TestDispatcherOboMapping:
    """Mapping login acteur → owner_id rag via le référentiel `users`."""

    async def _dispatcher(self, email: str | None):
        from unittest.mock import AsyncMock, MagicMock

        from rag.api.mcp_standard import RagMcpDispatcher, build_mcp_asgi

        disp = RagMcpDispatcher(build_mcp_asgi())
        pool = MagicMock()
        pool.fetchval = AsyncMock(return_value=email)
        state = MagicMock()
        state.pools = MagicMock()
        state.pools.config_pool = pool
        state.resolver = MagicMock()
        state.client_provider = MagicMock()
        disp.set_app_state(state)
        return disp

    async def test_known_login_maps_to_owner_id(self) -> None:
        from rag.auth.owner import email_to_owner_id

        disp = await self._dispatcher("gael@example.com")
        owner = await disp._resolve_obo_owner("gael")
        assert owner == email_to_owner_id("gael@example.com")

    async def test_unknown_login_returns_none(self) -> None:
        disp = await self._dispatcher(None)
        assert await disp._resolve_obo_owner("ghost") is None
