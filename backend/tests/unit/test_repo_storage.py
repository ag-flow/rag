from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from rag.sync.repo_storage import RepoStorage


def test_path_for_returns_nested_path() -> None:
    storage = RepoStorage(root=Path("/var/lib/rag/repos"))
    ws_id = UUID("11111111-1111-1111-1111-111111111111")
    src_id = UUID("22222222-2222-2222-2222-222222222222")
    p = storage.path_for(workspace_id=ws_id, source_id=src_id)
    assert p == Path(
        "/var/lib/rag/repos/11111111-1111-1111-1111-111111111111/"
        "22222222-2222-2222-2222-222222222222"
    )


def test_ensure_exists_creates_directory(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    p = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    assert p.exists()
    assert p.is_dir()


def test_ensure_exists_idempotent(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    p1 = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    p2 = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    assert p1 == p2
    assert p1.exists()


def test_has_git_returns_false_when_no_clone(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    assert storage.has_git(workspace_id=ws_id, source_id=src_id) is False


def test_has_git_returns_true_when_dot_git_exists(tmp_path: Path) -> None:
    storage = RepoStorage(root=tmp_path)
    ws_id = uuid4()
    src_id = uuid4()
    p = storage.ensure_exists(workspace_id=ws_id, source_id=src_id)
    (p / ".git").mkdir()
    assert storage.has_git(workspace_id=ws_id, source_id=src_id) is True
