from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from rag.schemas.sync import (
    ChangeSet,
    DueSource,
    GitOpResult,
    JobToProcess,
)


def test_change_set_defaults_empty_lists() -> None:
    cs = ChangeSet()
    assert cs.added == []
    assert cs.modified == []
    assert cs.deleted == []


def test_change_set_total_files_property() -> None:
    cs = ChangeSet(added=["a.md", "b.md"], modified=["c.md"], deleted=["d.md"])
    assert cs.total_changed == 4


def test_git_op_result_requires_current_commit() -> None:
    with pytest.raises(ValidationError):
        GitOpResult(was_fresh_clone=True)  # type: ignore[call-arg]


def test_git_op_result_minimal() -> None:
    r = GitOpResult(was_fresh_clone=False, current_commit="abc123")
    assert r.was_fresh_clone is False
    assert r.current_commit == "abc123"


def test_due_source_validates_workspace_and_source_ids() -> None:
    src = DueSource(
        source_id=uuid4(),
        workspace_id=uuid4(),
        config={"url": "https://github.com/x/y", "branch": "main"},
    )
    assert src.config["url"] == "https://github.com/x/y"


def test_job_to_process_requires_workspace_and_indexer_config() -> None:
    j = JobToProcess(
        job_id=uuid4(),
        workspace_id=uuid4(),
        workspace_name="ws_x",
        source_id=uuid4(),
        source_config={"url": "https://github.com/x/y", "branch": "main"},
        indexer_provider="openai",
        indexer_model="text-embedding-3-small",
        triggered_by="scheduled",
        correlation_id=None,
    )
    assert j.indexer_used == "openai/text-embedding-3-small"
