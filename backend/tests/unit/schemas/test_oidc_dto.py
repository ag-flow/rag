from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.oidc import (
    MeResponse,
    OidcConfigCreate,
    OidcConfigRead,
    OidcUserContext,
)


def test_oidc_config_create_accepts_valid_payload() -> None:
    cfg = OidcConfigCreate(
        issuer="https://keycloak.yoops.org/realms/homelab",
        client_id="rag-service",
        client_secret_ref="keycloak_rag_client_secret",
    )
    assert str(cfg.issuer) == "https://keycloak.yoops.org/realms/homelab"
    assert cfg.client_id == "rag-service"


def test_oidc_config_create_rejects_non_url_issuer() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="not-a-url",
            client_id="rag-service",
            client_secret_ref="x",
        )


def test_oidc_config_create_rejects_empty_client_id() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="https://keycloak.yoops.org/realms/homelab",
            client_id="",
            client_secret_ref="x",
        )


def test_oidc_config_create_rejects_empty_client_secret_ref() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="https://keycloak.yoops.org/realms/homelab",
            client_id="rag-service",
            client_secret_ref="",
        )


def test_oidc_config_create_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="https://keycloak.yoops.org/realms/homelab",
            client_id="rag-service",
            client_secret_ref="x",
            extra_field="rejected",
        )


def test_oidc_config_read_serializes_full() -> None:
    cfg = OidcConfigRead(
        issuer="https://keycloak.yoops.org/realms/homelab",
        client_id="rag-service",
        client_secret_ref="keycloak_rag_client_secret",
    )
    d = cfg.model_dump()
    assert d["issuer"] == "https://keycloak.yoops.org/realms/homelab"


def test_me_response_serializes_with_optional_fields() -> None:
    r = MeResponse(
        sub="user-uuid",
        email=None,
        name=None,
        roles=["rag-viewer"],
    )
    d = r.model_dump()
    assert d["email"] is None
    assert d["roles"] == ["rag-viewer"]


def test_oidc_user_context_is_frozen() -> None:
    import dataclasses

    ctx = OidcUserContext(sub="x", email=None, name=None, roles=[])
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.sub = "other"  # type: ignore[misc]
