from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.api.errors import (
    OidcInvalidToken,
    OidcNotConfigured,
    OidcRoleForbidden,
    OidcSessionExpired,
    OidcSessionMissing,
)
from rag.auth.oidc_dependency import _role_grants, require_oidc_role
from rag.services.oidc import OidcConfig


def test_role_grants_exact_match() -> None:
    assert _role_grants("rag-admin", user_roles=["rag-admin"]) is True
    assert _role_grants("rag-viewer", user_roles=["rag-viewer"]) is True


def test_role_grants_admin_includes_viewer() -> None:
    """Hierarchy : rag-admin a tous les droits du rag-viewer."""
    assert _role_grants("rag-viewer", user_roles=["rag-admin"]) is True


def test_role_grants_viewer_does_not_include_admin() -> None:
    assert _role_grants("rag-admin", user_roles=["rag-viewer"]) is False


def test_role_grants_returns_false_when_no_role() -> None:
    assert _role_grants("rag-viewer", user_roles=[]) is False


def _fake_request(
    *,
    session: dict[str, Any] | None,
    oidc_service: MagicMock,
    db_role: str | None = None,
) -> SimpleNamespace:
    """`db_role` : le rôle du compte en BASE, seule source d'autorisation."""
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=db_role)
    return SimpleNamespace(
        session=session if session is not None else {},
        app=SimpleNamespace(
            state=SimpleNamespace(oidc=oidc_service, pools=SimpleNamespace(config_pool=pool))
        ),
    )


def _session(**extra: Any) -> dict[str, Any]:
    exp_future = int(time.time()) + 300
    return {
        "_oidc_session": {
            "id_token": "x.y.z",
            "refresh_token": "rt",
            "exp": exp_future,
            "user_id": "11111111-1111-1111-1111-111111111111",
            **extra,
        }
    }


@pytest.mark.asyncio
async def test_dependency_raises_session_missing_when_no_session() -> None:
    oidc = MagicMock()
    req = _fake_request(session={}, oidc_service=oidc)
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcSessionMissing):
        await dep(req)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dependency_raises_session_expired_when_token_expired() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(side_effect=OidcInvalidToken("expired"))
    oidc.get_config = AsyncMock(
        return_value=OidcConfig(
            issuer="https://kc.example.com/realms/r",
            client_id="rag-service",
        )
    )
    exp_now = int(time.time())
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x.y.z", "refresh_token": "rt", "exp": exp_now}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcSessionExpired):
        await dep(req)  # type: ignore[arg-type]


def _oidc(claims: dict[str, Any]) -> MagicMock:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value=claims)
    oidc.get_config = AsyncMock(
        return_value=OidcConfig(issuer="https://kc.example.com/realms/r", client_id="rag-service")
    )
    return oidc


@pytest.mark.asyncio
async def test_dependency_returns_user_context_with_role_from_database() -> None:
    oidc = _oidc({"sub": "user-uuid", "email": "user@example.com", "name": "Test User"})
    req = _fake_request(session=_session(), oidc_service=oidc, db_role="rag-admin")
    ctx = await require_oidc_role("rag-admin")(req)  # type: ignore[arg-type]
    assert (ctx.sub, ctx.email, ctx.roles) == ("user-uuid", "user@example.com", ["rag-admin"])


@pytest.mark.asyncio
async def test_dependency_admin_grants_viewer_endpoint() -> None:
    req = _fake_request(session=_session(), oidc_service=_oidc({"sub": "u"}), db_role="rag-admin")
    ctx = await require_oidc_role("rag-viewer")(req)  # type: ignore[arg-type]
    assert "rag-admin" in ctx.roles


@pytest.mark.asyncio
async def test_dependency_viewer_cannot_access_admin_endpoint() -> None:
    req = _fake_request(session=_session(), oidc_service=_oidc({"sub": "u"}), db_role="rag-viewer")
    with pytest.raises(OidcRoleForbidden) as exc:
        await require_oidc_role("rag-admin")(req)  # type: ignore[arg-type]
    assert exc.value.required == "rag-admin"
    assert "rag-viewer" in exc.value.has


@pytest.mark.asyncio
async def test_dependency_ignores_roles_carried_by_token() -> None:
    """Le token dit admin, la base dit viewer : c'est la base qui décide (§1, §9)."""
    claims = {"sub": "u", "resource_access": {"rag-service": {"roles": ["rag-admin"]}}}
    oidc = _oidc(claims)
    oidc.extract_roles = MagicMock(return_value=["rag-admin"])
    req = _fake_request(session=_session(), oidc_service=oidc, db_role="rag-viewer")
    with pytest.raises(OidcRoleForbidden):
        await require_oidc_role("rag-admin")(req)  # type: ignore[arg-type]
    oidc.extract_roles.assert_not_called()


@pytest.mark.asyncio
async def test_dependency_session_without_anchored_user_forces_relogin() -> None:
    """Session ouverte avant l'ancrage (pas de user_id) : on ne devine pas le compte."""
    session = _session()
    del session["_oidc_session"]["user_id"]
    req = _fake_request(session=session, oidc_service=_oidc({"sub": "u"}), db_role="rag-admin")
    with pytest.raises(OidcSessionMissing):
        await require_oidc_role("rag-viewer")(req)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dependency_raises_not_configured_when_oidc_absent() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value={"sub": "u"})
    oidc.get_config = AsyncMock(return_value=None)
    exp_future = int(time.time()) + 300
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x", "refresh_token": "rt", "exp": exp_future}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcNotConfigured):
        await dep(req)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dependency_raises_session_missing_when_id_token_absent() -> None:
    """Session cookie présent mais sans clef id_token → OidcSessionMissing (ligne 52)."""
    oidc = MagicMock()
    oidc.get_config = AsyncMock(
        return_value=OidcConfig(
            issuer="https://kc.example.com/realms/r",
            client_id="rag-service",
        )
    )
    req = _fake_request(
        session={"_oidc_session": {"refresh_token": "rt"}},  # pas de id_token
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcSessionMissing):
        await dep(req)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dependency_reraises_non_expired_invalid_token() -> None:
    """OidcInvalidToken avec reason != 'expired' doit être re-levée telle quelle (ligne 59)."""
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(side_effect=OidcInvalidToken("bad_signature"))
    oidc.get_config = AsyncMock(
        return_value=OidcConfig(
            issuer="https://kc.example.com/realms/r",
            client_id="rag-service",
        )
    )
    exp_future = int(time.time()) + 300
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x.y.z", "refresh_token": "rt", "exp": exp_future}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcInvalidToken) as exc:
        await dep(req)  # type: ignore[arg-type]
    assert exc.value.reason == "bad_signature"
