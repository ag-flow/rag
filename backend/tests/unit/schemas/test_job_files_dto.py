from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.admin import JobFileEntry, JobFilesResponse


def test_job_file_entry_valid() -> None:
    e = JobFileEntry.model_validate({"path": "docs/a.md", "change_type": "added"})
    assert e.path == "docs/a.md"
    assert e.change_type == "added"


def test_job_file_entry_rejects_bad_change_type() -> None:
    with pytest.raises(ValidationError):
        JobFileEntry.model_validate({"path": "a.md", "change_type": "renamed"})


def test_job_files_response_shape() -> None:
    resp = JobFilesResponse.model_validate(
        {
            "files": [{"path": "a.md", "change_type": "deleted"}],
            "total": 1,
            "limit": 1000,
        }
    )
    assert resp.total == 1
    assert resp.limit == 1000
    assert resp.files[0].change_type == "deleted"
