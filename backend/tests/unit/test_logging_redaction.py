"""Le journal d'accès uvicorn ne garde pas le code/state du retour Harpocrate."""

from __future__ import annotations

import logging

from rag.logging_setup import _RedactSensitiveQueryFilter, setup_logging


def _record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", path, "1.1", 303),
        None,
    )


def test_connect_callback_query_masked_in_access_log() -> None:
    record = _record("/api/admin/harpocrate-vaults/connect/callback?code=SECRET&state=S")
    assert _RedactSensitiveQueryFilter().filter(record)
    message = record.getMessage()
    assert "SECRET" not in message and "state=S" not in message
    assert "/api/admin/harpocrate-vaults/connect/callback?<masqué>" in message


def test_other_routes_keep_their_query_string() -> None:
    record = _record("/api/v1/jobs?workspace=docflow-docs")
    _RedactSensitiveQueryFilter().filter(record)
    assert "workspace=docflow-docs" in record.getMessage()


def test_setup_logging_installs_filter_once() -> None:
    setup_logging("INFO", "dev")
    setup_logging("INFO", "dev")
    filters = logging.getLogger("uvicorn.access").filters
    assert sum(isinstance(f, _RedactSensitiveQueryFilter) for f in filters) == 1
