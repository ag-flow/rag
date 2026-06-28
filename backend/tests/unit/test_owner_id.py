from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest

from rag.auth.owner import _SYSTEM_OWNER_EMAIL, email_to_owner_id, get_current_owner_id


def test_email_to_owner_id_is_sha256_lower() -> None:
    expected = hashlib.sha256("admin@rag.io".encode()).hexdigest()
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
