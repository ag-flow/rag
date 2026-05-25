from __future__ import annotations

import pytest

from rag.secrets.refs import build_ref, is_vault_ref, parse_ref


@pytest.mark.parametrize(
    "ref, expected",
    [
        ("${vault://rag:openai_key}", ("rag", "openai_key")),
        ("${vault://prod-v2:secrets/keycloak/client}", ("prod-v2", "secrets/keycloak/client")),
        ("${vault://a:b}", ("a", "b")),
    ],
)
def test_parse_ref_valid(ref, expected):
    assert parse_ref(ref) == expected


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "openai_key",
        "${vault://rag}",
        "${vault://rag:}",
        "${vault://:path}",
        "vault://rag:path",
        "${vault://rag:path}extra",
        "prefix${vault://rag:path}",
    ],
)
def test_parse_ref_invalid_raises(ref):
    with pytest.raises(ValueError, match="ref Harpocrate invalide"):
        parse_ref(ref)


def test_build_ref_roundtrip():
    assert build_ref("rag", "openai_key") == "${vault://rag:openai_key}"
    assert parse_ref(build_ref("prod", "secrets/x/y")) == ("prod", "secrets/x/y")


def test_is_vault_ref():
    assert is_vault_ref("${vault://rag:openai_key}") is True
    assert is_vault_ref("plain string") is False
    assert is_vault_ref("") is False
