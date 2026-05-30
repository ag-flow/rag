from __future__ import annotations

import base64
import hashlib
import hmac

from rag.sync.webhook_validators import validate

PAYLOAD = b'{"ref":"refs/heads/main"}'
SECRET = "mysecret"


def _github_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_github_valid() -> None:
    headers = {"x-hub-signature-256": _github_sig(PAYLOAD, SECRET)}
    assert validate("github", SECRET, headers, PAYLOAD) is True


def test_github_invalid_sig() -> None:
    headers = {"x-hub-signature-256": "sha256=badbad"}
    assert validate("github", SECRET, headers, PAYLOAD) is False


def test_github_missing_header() -> None:
    assert validate("github", SECRET, {}, PAYLOAD) is False


def _gitea_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return mac.hexdigest()


def test_gitea_valid() -> None:
    headers = {"x-gitea-signature": _gitea_sig(PAYLOAD, SECRET)}
    assert validate("gitea", SECRET, headers, PAYLOAD) is True


def test_gitea_invalid() -> None:
    headers = {"x-gitea-signature": "badhex"}
    assert validate("gitea", SECRET, headers, PAYLOAD) is False


def test_gitlab_valid() -> None:
    headers = {"x-gitlab-token": SECRET}
    assert validate("gitlab", SECRET, headers, PAYLOAD) is True


def test_gitlab_invalid() -> None:
    headers = {"x-gitlab-token": "wrongtoken"}
    assert validate("gitlab", SECRET, headers, PAYLOAD) is False


def test_gitlab_missing() -> None:
    assert validate("gitlab", SECRET, {}, PAYLOAD) is False


def _bitbucket_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def test_bitbucket_valid() -> None:
    headers = {"x-hub-signature": _bitbucket_sig(PAYLOAD, SECRET)}
    assert validate("bitbucket", SECRET, headers, PAYLOAD) is True


def test_bitbucket_invalid() -> None:
    headers = {"x-hub-signature": "sha256=bad"}
    assert validate("bitbucket", SECRET, headers, PAYLOAD) is False


def _azure_basic(secret: str) -> str:
    return "Basic " + base64.b64encode(f":{secret}".encode()).decode()


def test_azure_valid() -> None:
    headers = {"authorization": _azure_basic(SECRET)}
    assert validate("azure-devops", SECRET, headers, PAYLOAD) is True


def test_azure_invalid() -> None:
    headers = {"authorization": "Basic " + base64.b64encode(b":wrong").decode()}
    assert validate("azure-devops", SECRET, headers, PAYLOAD) is False


def test_azure_missing() -> None:
    assert validate("azure-devops", SECRET, {}, PAYLOAD) is False


def test_unknown_provider_returns_false() -> None:
    assert validate("unknown", SECRET, {}, PAYLOAD) is False
