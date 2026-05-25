from __future__ import annotations

import time

import bcrypt
import pytest

from rag.services.local_auth import LocalAuthService


@pytest.fixture
def known_hash() -> str:
    """Hash bcrypt de 'correctpwd' avec cost minimal pour tests rapides."""
    return bcrypt.hashpw(b"correctpwd", bcrypt.gensalt(rounds=4)).decode()


def test_verify_correct_credentials_returns_true(known_hash: str) -> None:
    svc = LocalAuthService(username="admin", password_hash=known_hash, ttl_seconds=3600)
    assert svc.verify(username="admin", password="correctpwd") is True


def test_verify_wrong_password_returns_false(known_hash: str) -> None:
    svc = LocalAuthService(username="admin", password_hash=known_hash, ttl_seconds=3600)
    assert svc.verify(username="admin", password="wrong") is False


def test_verify_wrong_username_returns_false(known_hash: str) -> None:
    svc = LocalAuthService(username="admin", password_hash=known_hash, ttl_seconds=3600)
    assert svc.verify(username="root", password="correctpwd") is False


def test_verify_when_disabled_returns_false() -> None:
    """password_hash vide -> enabled=False -> verify retourne toujours False."""
    svc = LocalAuthService(username="admin", password_hash="", ttl_seconds=3600)
    assert svc.enabled is False
    assert svc.verify(username="admin", password="anything") is False


def test_verify_malformed_hash_returns_false() -> None:
    """Hash non bcrypt valide -> False sans crash (pas de validation au boot)."""
    svc = LocalAuthService(username="admin", password_hash="not-a-bcrypt-hash", ttl_seconds=3600)
    assert svc.verify(username="admin", password="anything") is False


def test_build_session_payload_with_ttl_sets_correct_expiry(known_hash: str) -> None:
    svc = LocalAuthService(username="admin", password_hash=known_hash, ttl_seconds=3600)
    before = int(time.time())
    payload = svc.build_session_payload()
    after = int(time.time())
    assert payload["username"] == "admin"
    assert before + 3600 <= payload["expires_at"] <= after + 3600
