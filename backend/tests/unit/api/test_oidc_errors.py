from __future__ import annotations

from rag.api.errors import (
    AdminError,
    OidcInvalidCode,
    OidcInvalidSession,
    OidcInvalidToken,
    OidcKeycloakUnreachable,
    OidcNotConfigured,
    OidcRoleForbidden,
    OidcSessionExpired,
    OidcSessionMissing,
    OidcStateMismatch,
    OidcStateMissing,
)


def test_oidc_not_configured_payload() -> None:
    e = OidcNotConfigured()
    assert isinstance(e, AdminError)
    assert e.http_status == 503
    assert e.to_payload() == {
        "error": "oidc_not_configured",
        "message": "POST /admin/oidc avec la master-key pour configurer Keycloak",
    }


def test_oidc_keycloak_unreachable_payload() -> None:
    e = OidcKeycloakUnreachable("https://kc.example.com/realms/homelab")
    assert e.http_status == 503
    assert e.to_payload() == {
        "error": "oidc_keycloak_unreachable",
        "issuer": "https://kc.example.com/realms/homelab",
    }


def test_oidc_state_missing_payload() -> None:
    e = OidcStateMissing()
    assert e.http_status == 400
    assert e.to_payload() == {"error": "oidc_state_missing"}


def test_oidc_state_mismatch_payload() -> None:
    e = OidcStateMismatch()
    assert e.http_status == 400
    assert e.to_payload() == {"error": "oidc_state_mismatch"}


def test_oidc_invalid_code_payload() -> None:
    e = OidcInvalidCode("invalid_grant")
    assert e.http_status == 400
    assert e.to_payload() == {
        "error": "oidc_invalid_code",
        "reason": "invalid_grant",
    }


def test_oidc_session_missing_payload() -> None:
    e = OidcSessionMissing()
    assert e.http_status == 401
    assert e.to_payload() == {"error": "oidc_session_missing"}


def test_oidc_invalid_session_payload() -> None:
    e = OidcInvalidSession()
    assert e.http_status == 401
    assert e.to_payload() == {"error": "oidc_invalid_session"}


def test_oidc_session_expired_payload() -> None:
    e = OidcSessionExpired()
    assert e.http_status == 401
    assert e.to_payload() == {"error": "oidc_session_expired"}


def test_oidc_invalid_token_payload() -> None:
    e = OidcInvalidToken("signature_invalid")
    assert e.http_status == 401
    assert e.to_payload() == {
        "error": "oidc_invalid_token",
        "reason": "signature_invalid",
    }


def test_oidc_role_forbidden_payload() -> None:
    e = OidcRoleForbidden(required="rag-admin", has=["rag-viewer"])
    assert e.http_status == 403
    assert e.to_payload() == {
        "error": "oidc_role_forbidden",
        "required": "rag-admin",
        "has": ["rag-viewer"],
    }
