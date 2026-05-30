from __future__ import annotations

import inspect

from rag.sync.scheduler import schedule_due_sources


def test_scheduler_query_excludes_webhook_enabled() -> None:
    """Le SQL de schedule_due_sources doit filtrer webhook_enabled = false."""
    src = inspect.getsource(schedule_due_sources)
    assert "webhook_enabled" in src
    assert "false" in src.lower()
