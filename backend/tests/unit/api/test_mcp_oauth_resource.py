"""Surface MCP en serveur de ressources OAuth 2.1 (ticket 3d457a26).

IdP simulé : JWKS servi par un transport httpx factice, jetons signés
localement. Le dispatcher réel est éprouvé avec une app interne « sonde » qui
capture le contexte d'authentification posé pour les outils.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from rag.api.mcp_standard import RagMcpDispatcher, _ws_ctx
from rag.auth.mcp_resource import ROLE_TO_SCOPE, looks_like_jwt, protected_resource_metadata
from rag.services.oidc import OidcConfig, OidcService

ISSUER = "https://idp.example/realms/yoops"
PUBLIC = "https://rag.yoops.org"
RESOURCE = f"{PUBLIC}/mcp"
METADATA = f"{PUBLIC}/.well-known/oauth-protected-resource/mcp"
_KEY = RSAKey.generate_key(key_size=2048, private=True)
_KID = "k1"


def _token(**over: Any) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": RESOURCE, "sub": "sub-42", "exp": now + 300, "iat": now}
    claims.update(over)
    return jwt.encode({"alg": "RS256", "kid": _KID, "typ": "JWT"}, claims, _KEY)


def _oidc() -> OidcService:
    def handler(request: httpx.Request) -> httpx.Response:
        if "well-known" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "end_session_endpoint": f"{ISSUER}/logout",
                    "jwks_uri": f"{ISSUER}/jwks",
                },
            )
        pub = _KEY.as_dict(private=False) | {"kid": _KID, "alg": "RS256", "use": "sig"}
        return httpx.Response(200, json={"keys": [pub]})

    svc = OidcService(
        config_pool=None,
        public_url=PUBLIC,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    svc.get_config = AsyncMock(return_value=OidcConfig(issuer=ISSUER, client_id="ragflow-ui"))  # type: ignore[method-assign]
    return svc


class _Probe:
    """App interne : note le contexte posé par le dispatcher, répond 200."""

    def __init__(self) -> None:
        self.ctx: Any = None

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        self.ctx = _ws_ctx.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def _dispatcher(*, user: dict[str, Any] | None, api_key: dict[str, Any] | None = None):  # type: ignore[no-untyped-def]
    probe = _Probe()
    disp = RagMcpDispatcher(probe)
    pool = MagicMock()

    async def fetchrow(sql: str, *args: Any) -> Any:
        if "FROM users" in sql:
            assert args == (ISSUER, "sub-42")  # ancrage (issuer, sub), jamais l'email
            return user
        return api_key

    pool.fetchrow = fetchrow
    state = MagicMock()
    state.pools.config_pool = pool
    state.client_provider.get_default_vault_name = AsyncMock(return_value=None)
    state.admin_env.get_public_url = MagicMock(return_value=PUBLIC)
    state.settings.rag_mcp_resource = None
    state.oidc = _oidc()
    disp.set_app_state(state)
    return disp, probe


async def _call(disp: RagMcpDispatcher, token: str | None, extra: list | None = None):  # type: ignore[no-untyped-def]
    headers = [(b"host", b"rag.yoops.org")] + (extra or [])
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {"type": "http", "path": "/", "headers": headers, "method": "POST"}
    sent: list[dict[str, Any]] = []

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    await disp(scope, AsyncMock(), send)
    start = sent[0]
    head = {k.decode(): v.decode() for k, v in start["headers"]}
    body = json.loads(sent[1]["body"] or b"{}")
    return start["status"], head, body


ADMIN = {"owner_id": "owner-admin", "role": "rag-admin"}
VIEWER = {"owner_id": "owner-viewer", "role": "rag-viewer"}


@pytest.mark.asyncio
async def test_no_token_401_points_to_resource_metadata() -> None:
    disp, probe = _dispatcher(user=ADMIN)
    status, head, body = await _call(disp, None)
    assert status == 401 and body == {"error": "authorization_required"}
    assert head["www-authenticate"] == f'Bearer resource_metadata="{METADATA}"'
    assert probe.ctx is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("user", "scope"), [(ADMIN, "admin"), (VIEWER, "read")])
async def test_idp_token_gets_role_scope_and_token_owner(user, scope) -> None:
    disp, probe = _dispatcher(user=user)
    status, _head, _body = await _call(disp, _token())
    assert status == 200
    assert (probe.ctx.owner_id, probe.ctx.scope, probe.ctx.owner_source) == (
        user["owner_id"],
        scope,
        "oidc",
    )


@pytest.mark.asyncio
async def test_idp_token_scope_matches_api_key_of_same_level() -> None:
    """Parité : un jeton de rôle rag-viewer porte EXACTEMENT le contexte d'une
    clé `read` — les outils ne lisent que ce champ."""
    disp, probe = _dispatcher(user=VIEWER)
    await _call(disp, _token())
    via_token = probe.ctx
    disp, probe = _dispatcher(
        user=None,
        api_key={"owner_id": "owner-viewer", "scope": "read", "require_obo": False},
    )
    await _call(disp, "clefopaque48caracteresbase64urlsanspoint_________")
    assert (via_token.owner_id, via_token.scope) == (probe.ctx.owner_id, probe.ctx.scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"aud": "https://devpod.yoops.org/mcp"}, "audience"),
        ({"aud": "ragflow-ui"}, "audience"),
        ({"iss": "https://autre-idp.example/realms/x"}, "invalid_claim:iss"),
        ({"exp": int(time.time()) - 60}, "expired"),
    ],
)
async def test_idp_token_refused_401_with_reason(over, reason) -> None:
    disp, probe = _dispatcher(user=ADMIN)
    status, head, body = await _call(disp, _token(**over))
    assert (status, body) == (401, {"error": reason})
    expected = f'Bearer resource_metadata="{METADATA}", error="invalid_token"'
    assert head["www-authenticate"] == expected
    assert probe.ctx is None


@pytest.mark.asyncio
async def test_idp_token_forged_signature_refused() -> None:
    other = RSAKey.generate_key(key_size=2048, private=True)
    now = int(time.time())
    forged = jwt.encode(
        {"alg": "RS256", "kid": _KID},
        {"iss": ISSUER, "aud": RESOURCE, "sub": "sub-42", "exp": now + 300},
        other,
    )
    disp, probe = _dispatcher(user=ADMIN)
    status, _head, body = await _call(disp, forged)
    assert (status, body) == (401, {"error": "bad_signature"})
    assert probe.ctx is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user", "reason"),
    [(None, "user_not_provisioned"), ({"owner_id": "o", "role": None}, "role_unknown")],
)
async def test_idp_token_valid_but_no_right_403(user, reason) -> None:
    disp, probe = _dispatcher(user=user)
    status, head, body = await _call(disp, _token())
    assert (status, body) == (403, {"error": reason})
    assert 'error="insufficient_scope"' in head["www-authenticate"]
    assert probe.ctx is None


@pytest.mark.asyncio
async def test_idp_token_ignores_obo_headers(monkeypatch) -> None:
    """L'humain EST le porteur : la résolution OBO n'est pas consultée sur ce
    chemin, des en-têtes d'identité ne peuvent pas remplacer le `sub`."""
    spy = AsyncMock(return_value="owner-usurpe")
    monkeypatch.setattr("rag.api.mcp_standard.resolve_effective_owner_id", spy)
    disp, probe = _dispatcher(user=VIEWER)
    obo = [(b"x-portal-actor", b"autre@example.com"), (b"x-portal-actor-signature", b"x")]
    await _call(disp, _token(), extra=obo)
    assert probe.ctx.owner_id == "owner-viewer"
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_api_key_401_flags_invalid_token() -> None:
    disp, _probe = _dispatcher(user=None, api_key=None)
    status, head, body = await _call(disp, "clefinconnue")
    assert (status, body) == (401, {"error": "invalid_token"})
    assert head["www-authenticate"].endswith('error="invalid_token"')


def test_api_key_alphabet_never_looks_like_jwt() -> None:
    assert looks_like_jwt(_token())
    assert not looks_like_jwt("AbC-_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGH")


def test_metadata_announces_issuer_for_resource() -> None:
    assert protected_resource_metadata(RESOURCE, ISSUER) == {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "bearer_methods_supported": ["header"],
        "resource_name": "ragflow — recherche sémantique",
    }
    assert set(ROLE_TO_SCOPE.values()) <= {"read", "read_write", "admin"}
