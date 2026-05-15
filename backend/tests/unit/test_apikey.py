from __future__ import annotations

import re

import pytest

from rag.services.apikey import generate_api_key, hash_api_key, verify_api_key


def test_generate_api_key_length_48() -> None:
    key = generate_api_key()
    assert len(key) == 48


def test_generate_api_key_url_safe_charset() -> None:
    key = generate_api_key()
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", key)


def test_generate_api_key_random() -> None:
    keys = {generate_api_key() for _ in range(100)}
    assert len(keys) == 100  # collisions extrêmement improbables


def test_hash_api_key_is_bcrypt_format() -> None:
    h = hash_api_key("any-key")
    assert h.startswith("$2b$12$")


def test_verify_api_key_round_trip() -> None:
    key = generate_api_key()
    h = hash_api_key(key)
    assert verify_api_key(key, h) is True


def test_verify_api_key_wrong_key() -> None:
    key = generate_api_key()
    h = hash_api_key(key)
    assert verify_api_key("wrong-key", h) is False


def test_verify_api_key_invalid_hash() -> None:
    assert verify_api_key("any", "not-a-bcrypt-hash") is False


def test_hash_api_key_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        hash_api_key("")
