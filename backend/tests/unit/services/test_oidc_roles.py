from __future__ import annotations

from rag.services.oidc import OidcService


def test_extract_roles_present_in_resource_access() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    claims = {
        "resource_access": {
            "rag-service": {"roles": ["rag-admin", "rag-viewer"]},
            "other-client": {"roles": ["other-role"]},
        },
    }
    assert svc.extract_roles(claims, "rag-service") == ["rag-admin", "rag-viewer"]


def test_extract_roles_returns_empty_when_resource_access_absent() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    assert svc.extract_roles({}, "rag-service") == []


def test_extract_roles_returns_empty_when_client_id_absent() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    claims = {"resource_access": {"other-client": {"roles": ["x"]}}}
    assert svc.extract_roles(claims, "rag-service") == []


def test_extract_roles_returns_empty_when_roles_absent() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    claims = {"resource_access": {"rag-service": {}}}
    assert svc.extract_roles(claims, "rag-service") == []
