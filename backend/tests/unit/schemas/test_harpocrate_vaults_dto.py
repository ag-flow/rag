from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from rag.schemas.harpocrate_vaults import (
    SecretListItem,
    SecretListResponse,
    SecretTypeSummary,
    VaultCreateRequest,
    VaultRotateApiKeyRequest,
    VaultUpdateRequest,
    WalletInfoResponse,
)


def _valid_create_payload(**overrides):
    payload = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "secretvalueX" * 4,
        "is_default": True,
    }
    payload.update(overrides)
    return payload


def test_create_valid():
    req = VaultCreateRequest(**_valid_create_payload())
    assert req.name == "rag"
    assert req.base_url == "https://harpocrate.yoops.org"


@pytest.mark.parametrize(
    "bad_name",
    [
        "A",
        "ra",
        "1rag",
        "rag!",
        "rag space",
        "_rag",
        "x" * 65,
    ],
)
def test_create_name_validation(bad_name):
    with pytest.raises(ValidationError):
        VaultCreateRequest(**_valid_create_payload(name=bad_name))


def test_create_base_url_strips_trailing_slash():
    req = VaultCreateRequest(**_valid_create_payload(base_url="https://h.org/"))
    assert req.base_url == "https://h.org"


def test_create_base_url_requires_http_scheme():
    with pytest.raises(ValidationError, match="http"):
        VaultCreateRequest(**_valid_create_payload(base_url="ftp://h.org"))


def test_create_probe_path_validation():
    req = VaultCreateRequest(**_valid_create_payload(probe_path="path/to/secret"))
    assert req.probe_path == "path/to/secret"
    with pytest.raises(ValidationError):
        VaultCreateRequest(**_valid_create_payload(probe_path="bad path with spaces"))
    req2 = VaultCreateRequest(**_valid_create_payload(probe_path=""))
    assert req2.probe_path is None


def test_update_forbids_name_field():
    with pytest.raises(ValidationError, match="extra"):
        VaultUpdateRequest(name="newname")


def test_update_forbids_is_default_field():
    with pytest.raises(ValidationError, match="extra"):
        VaultUpdateRequest(is_default=True)


def test_update_partial_label_only():
    req = VaultUpdateRequest(label="new label")
    assert req.label == "new label"
    assert req.base_url is None


def test_rotate_requires_both_fields():
    req = VaultRotateApiKeyRequest(api_key_id="k-002", api_key="newvalue1234")
    assert req.api_key_id == "k-002"
    with pytest.raises(ValidationError):
        VaultRotateApiKeyRequest(api_key="x" * 12)


def test_wallet_info_response_minimal():
    info = WalletInfoResponse(
        wallet_id=uuid4(),
        wallet_name=None,
        api_key_id="k-001",
        permissions=["read", "write"],
        api_key_expires_at=None,
    )
    assert info.permissions == ["read", "write"]
    assert info.wallet_name is None


def test_wallet_info_response_full():
    expires = datetime(2026, 12, 31, tzinfo=UTC)
    info = WalletInfoResponse(
        wallet_id=uuid4(),
        wallet_name="prod-wallet",
        api_key_id="k-001",
        permissions=["read"],
        api_key_expires_at=expires,
    )
    assert info.api_key_expires_at == expires


def test_secret_type_summary():
    t = SecretTypeSummary(
        type_uuid=uuid4(),
        type="openai_api_key",
        sous_type=None,
        label="OpenAI API key",
        deprecated=False,
    )
    assert t.type == "openai_api_key"
    assert t.deprecated is False


def test_secret_list_item():
    item = SecretListItem(
        id=uuid4(),
        name="anthropic_key",
        description=None,
        is_placeholder=False,
        tags=[],
    )
    assert item.name == "anthropic_key"
    assert item.tags == []


def test_secret_list_response_paginated():
    resp = SecretListResponse(
        secrets=[
            SecretListItem(
                id=uuid4(),
                name="k1",
                description=None,
                is_placeholder=False,
                tags=["env:prod"],
            ),
        ],
        next_cursor="opaque-cursor-1",
    )
    assert len(resp.secrets) == 1
    assert resp.next_cursor == "opaque-cursor-1"


def test_secret_list_response_no_cursor():
    resp = SecretListResponse(secrets=[], next_cursor=None)
    assert resp.next_cursor is None
