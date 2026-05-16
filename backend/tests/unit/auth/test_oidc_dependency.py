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
) -> SimpleNamespace:
    return SimpleNamespace(
        session=session if session is not None else {},
        app=SimpleNamespace(state=SimpleNamespace(oidc=oidc_service)),
    )


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
            client_secret_ref="x",
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


@pytest.mark.asyncio
async def test_dependency_returns_user_context_when_role_matches() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(
        return_value={
            "sub": "user-uuid",
            "email": "user@example.com",
            "name": "Test User",
            "resource_access": {"rag-service": {"roles": ["rag-admin"]}},
        }
    )
    oidc.get_config = AsyncMock(
        return_value=OidcConfig(
            issuer="https://kc.example.com/realms/r",
            client_id="rag-service",
            client_secret_ref="x",
        )
    )
    oidc.extract_roles = MagicMock(return_value=["rag-admin"])
    exp_future = int(time.time()) + 300
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x.y.z", "refresh_token": "rt", "exp": exp_future}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-admin")
    ctx = await dep(req)  # type: ignore[arg-type]
    assert ctx.sub == "user-uuid"
    assert ctx.email == "user@example.com"
    assert ctx.roles == ["rag-admin"]


@pytest.mark.asyncio
async def test_dependency_admin_grants_viewer_endpoint() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value={"sub": "u", "email": None, "name": None})
    oidc.get_config = AsyncMock(
        return_value=OidcConfig(
            issuer="https://kc.example.com/realms/r",
            client_id="rag-service",
            client_secret_ref="x",
        )
    )
    oidc.extract_roles = MagicMock(return_value=["rag-admin"])
    exp_future = int(time.time()) + 300
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x", "refresh_token": "rt", "exp": exp_future}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    ctx = await dep(req)  # type: ignore[arg-type]
    assert "rag-admin" in ctx.roles


@pytest.mark.asyncio
async def test_dependency_viewer_cannot_access_admin_endpoint() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value={"sub": "u", "email": None, "name": None})
    oidc.get_config = AsyncMock(
        return_value=OidcConfig(
            issuer="https://kc.example.com/realms/r",
            client_id="rag-service",
            client_secret_ref="x",
        )
    )
    oidc.extract_roles = MagicMock(return_value=["rag-viewer"])
    exp_future = int(time.time()) + 300
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x", "refresh_token": "rt", "exp": exp_future}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-admin")
    with pytest.raises(OidcRoleForbidden) as exc:
        await dep(req)  # type: ignore[arg-type]
    assert exc.value.required == "rag-admin"
    assert "rag-viewer" in exc.value.has


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
