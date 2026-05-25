from __future__ import annotations

import json

import pytest
import structlog

from rag.logging_setup import setup_logging


def test_setup_logging_console_dev(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(level="INFO", environment="dev")
    log = structlog.get_logger("test")
    log.info("hello", workspace="harpocrate")

    captured = capsys.readouterr().out
    assert "hello" in captured
    assert "harpocrate" in captured


def test_setup_logging_json_prod(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(level="INFO", environment="prod")
    log = structlog.get_logger("test")
    log.info("event", key="value")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["event"] == "event"
    assert parsed["key"] == "value"
    assert parsed["level"] == "info"
    assert "timestamp" in parsed


def test_setup_logging_filters_below_level(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(level="WARNING", environment="prod")
    log = structlog.get_logger("test")
    log.info("should_not_appear")
    log.warning("should_appear")

    output = capsys.readouterr().out
    assert "should_not_appear" not in output
    assert "should_appear" in output


def test_setup_logging_invalid_level_raises() -> None:
    with pytest.raises(ValueError, match="Invalid log level"):
        setup_logging(level="NOTALEVEL", environment="dev")
