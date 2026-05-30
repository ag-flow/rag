from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.services.llm_clients import build_prompt, call_llm


def test_build_prompt_includes_context_and_history() -> None:
    chunks = [
        {"path": "doc/a.md", "content": "Le gap handling utilise sync_shelf.", "score": 0.9},
    ]
    history = [
        {"role": "user", "content": "explique la réplication"},
        {"role": "assistant", "content": "La réplication repose sur MQTT."},
    ]
    system, messages = build_prompt(
        chunks=chunks,
        history=history,
        message="et le gap handling ?",
    )
    assert "sync_shelf" in system
    assert "doc/a.md" in system
    assert len(messages) == 3
    assert messages[-1]["role"] == "user"
    assert "gap handling" in messages[-1]["content"]


def test_build_prompt_no_chunks_signals_no_context() -> None:
    system, messages = build_prompt(chunks=[], history=[], message="question ?")
    assert len(system) > 0
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_call_llm_claude_returns_answer() -> None:
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Réponse Claude.")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("rag.services.llm_clients.anthropic") as mock_anthropic:
        mock_anthropic.AsyncAnthropic.return_value = mock_client
        result = await call_llm(
            provider="claude",
            model="claude-sonnet-4-5",
            api_key="sk-ant-test",
            base_url=None,
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert result["answer"] == "Réponse Claude."
    assert result["usage"]["prompt_tokens"] == 100
    assert result["usage"]["completion_tokens"] == 50


@pytest.mark.asyncio
async def test_call_llm_openai_returns_answer() -> None:
    mock_choice = MagicMock()
    mock_choice.message.content = "Réponse OpenAI."
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 80
    mock_response.usage.completion_tokens = 40

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("rag.services.llm_clients.openai") as mock_openai:
        mock_openai.AsyncOpenAI.return_value = mock_client
        result = await call_llm(
            provider="openai",
            model="gpt-4o",
            api_key="sk-test",
            base_url=None,
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert result["answer"] == "Réponse OpenAI."
    assert result["usage"]["prompt_tokens"] == 80
