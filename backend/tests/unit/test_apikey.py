from __future__ import annotations

import re

from rag.services.apikey import generate_api_key


def test_generate_api_key_length_48() -> None:
    key = generate_api_key()
    assert len(key) == 48


def test_generate_api_key_url_safe_charset() -> None:
    key = generate_api_key()
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", key)


def test_generate_api_key_random() -> None:
    keys = {generate_api_key() for _ in range(100)}
    assert len(keys) == 100  # collisions extrêmement improbables
