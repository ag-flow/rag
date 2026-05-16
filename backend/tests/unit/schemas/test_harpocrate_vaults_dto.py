from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultRotateApiKeyRequest,
    VaultUpdateRequest,
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
