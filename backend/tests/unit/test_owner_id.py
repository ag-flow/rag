from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

from rag.auth.owner import _SYSTEM_OWNER_EMAIL, email_to_owner_id, get_current_owner_id


def test_email_to_owner_id_is_sha256_lower() -> None:
    expected = hashlib.sha256(b"admin@rag.io").hexdigest()
    assert email_to_owner_id("admin@rag.io") == expected


def test_email_to_owner_id_lowercases() -> None:
    assert email_to_owner_id("Admin@RAG.io") == email_to_owner_id("admin@rag.io")


def test_get_current_owner_id_master_key_uses_system_owner() -> None:
    """Master key auth → owner système constant (pas lié à un utilisateur)."""
    request = MagicMock()
    request.headers.get.return_value = "Bearer somekey"

    result = get_current_owner_id(request)
    assert result == email_to_owner_id(_SYSTEM_OWNER_EMAIL)


def test_get_current_owner_id_local_session_uses_session_email() -> None:
    """Session locale → email stocké dans le payload de session."""
    request = MagicMock()
    request.headers.get.return_value = None
    request.session = {
        "_local_session": {
            "expires_at": 9999999999,
            "username": "admin",
            "email": "boss@example.com",
        }
    }

    result = get_current_owner_id(request)
    assert result == email_to_owner_id("boss@example.com")


def test_get_current_owner_id_local_session_missing_email_falls_back_to_system() -> None:
    """Session locale sans email (ancienne session) → owner système."""
    request = MagicMock()
    request.headers.get.return_value = None
    request.session = {
        "_local_session": {"expires_at": 9999999999, "username": "admin"}
    }

    result = get_current_owner_id(request)
    assert result == email_to_owner_id(_SYSTEM_OWNER_EMAIL)


def test_get_current_owner_id_oidc_session() -> None:
    """Session OIDC → email depuis payload JWT."""
    import base64
    import json

    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    payload_data = {"sub": "user123", "email": "alice@example.com", "exp": 9999999999}
    payload = base64.urlsafe_b64encode(
        json.dumps(payload_data).encode()
    ).rstrip(b"=").decode()
    fake_jwt = f"{header}.{payload}.fakesignature"

    request = MagicMock()
    request.headers.get.return_value = None
    request.session = {"_oidc_session": {"id_token": fake_jwt}}

    result = get_current_owner_id(request)
    assert result == email_to_owner_id("alice@example.com")


def test_get_current_owner_id_oidc_prefers_preferred_username() -> None:
    """Session OIDC → preferred_username (= owner_login portail, clé OBO), pas email.

    Garantit qu'un humain a le MÊME owner_id via sa session OIDC et via
    l'attribution OBO (qui dérive owner_id du même login)."""
    import base64
    import json

    from rag.auth.owner import principal_to_owner_id

    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    # preferred_username != email : c'est le login qui doit primer.
    payload_data = {"preferred_username": "gael", "email": "gael@corp.example", "exp": 9999999999}
    payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=").decode()
    fake_jwt = f"{header}.{payload}.sig"

    request = MagicMock()
    request.headers.get.return_value = None
    request.session = {"_oidc_session": {"id_token": fake_jwt}}

    # Même valeur que ce que produirait l'attribution OBO pour actor="gael".
    assert get_current_owner_id(request) == principal_to_owner_id("gael")
