from __future__ import annotations

from rag.sync.webhook_parsers import extract_branch


def test_github_push_ref() -> None:
    assert extract_branch("github", {"ref": "refs/heads/main"}) == "main"


def test_github_tag_ref_returns_none() -> None:
    assert extract_branch("github", {"ref": "refs/tags/v1.0"}) is None


def test_github_missing_ref() -> None:
    assert extract_branch("github", {}) is None


def test_gitea_same_as_github() -> None:
    assert extract_branch("gitea", {"ref": "refs/heads/dev"}) == "dev"


def test_gitlab_same_as_github() -> None:
    assert extract_branch("gitlab", {"ref": "refs/heads/feature-x"}) == "feature-x"


def test_bitbucket_push_new_name() -> None:
    payload = {"push": {"changes": [{"new": {"name": "main"}}]}}
    assert extract_branch("bitbucket", payload) == "main"


def test_bitbucket_missing_changes_returns_none() -> None:
    assert extract_branch("bitbucket", {"push": {"changes": []}}) is None


def test_bitbucket_no_push_key_returns_none() -> None:
    assert extract_branch("bitbucket", {}) is None


def test_azure_devops_ref_updates() -> None:
    payload = {"resource": {"refUpdates": [{"name": "refs/heads/main"}]}}
    assert extract_branch("azure-devops", payload) == "main"


def test_azure_devops_tag_returns_none() -> None:
    payload = {"resource": {"refUpdates": [{"name": "refs/tags/v1"}]}}
    assert extract_branch("azure-devops", payload) is None


def test_azure_devops_missing_returns_none() -> None:
    assert extract_branch("azure-devops", {}) is None


def test_unknown_provider_returns_none() -> None:
    assert extract_branch("unknown", {"ref": "refs/heads/main"}) is None
