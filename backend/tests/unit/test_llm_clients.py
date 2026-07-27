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


@pytest.mark.asyncio
async def test_call_llm_ollama_cloud_uses_bearer_and_default_url() -> None:
    """ollama-cloud : même API que le daemon local, mais https://ollama.com
    par défaut et clé API en Authorization Bearer."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {"content": "Réponse cloud."},
        "prompt_eval_count": 10,
        "eval_count": 5,
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("rag.services.llm_clients.httpx.AsyncClient", return_value=mock_client):
        result = await call_llm(
            provider="ollama-cloud",
            model="gpt-oss:120b-cloud",
            api_key="ok-test",
            base_url=None,
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "hello"}],
        )

    assert result["answer"] == "Réponse cloud."
    url = mock_client.post.call_args.args[0]
    assert url == "https://ollama.com/api/chat"
    headers = mock_client.post.call_args.kwargs["headers"]
    assert headers == {"Authorization": "Bearer ok-test"}


@pytest.mark.asyncio
async def test_call_llm_ollama_local_no_auth_header() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"message": {"content": "ok"}}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("rag.services.llm_clients.httpx.AsyncClient", return_value=mock_client):
        await call_llm(
            provider="ollama",
            model="llama3.1:8b",
            api_key=None,
            base_url="http://192.168.10.80:11434",
            system_prompt="s",
            messages=[{"role": "user", "content": "hello"}],
        )

    url = mock_client.post.call_args.args[0]
    assert url == "http://192.168.10.80:11434/api/chat"
    assert mock_client.post.call_args.kwargs["headers"] == {}


@pytest.mark.asyncio
async def test_call_llm_openai_compatible_providers_use_default_base_url() -> None:
    """gemini / deepseek / dashscope : client OpenAI pointé sur l'endpoint
    compatible du provider (surchargé par base_url si fournie)."""
    expected = {
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
        "deepseek": "https://api.deepseek.com/v1",
        "dashscope": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    }
    for provider, url in expected.items():
        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 1
        mock_response.usage.completion_tokens = 1

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("rag.services.llm_clients.openai") as mock_openai:
            mock_openai.AsyncOpenAI.return_value = mock_client
            result = await call_llm(
                provider=provider,
                model="m",
                api_key="k",
                base_url=None,
                system_prompt="s",
                messages=[{"role": "user", "content": "hello"}],
            )
        assert result["answer"] == "ok"
        mock_openai.AsyncOpenAI.assert_called_once_with(api_key="k", base_url=url)


@pytest.mark.asyncio
async def test_call_llm_openai_compatible_base_url_override() -> None:
    mock_choice = MagicMock()
    mock_choice.message.content = "ok"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 1
    mock_response.usage.completion_tokens = 1

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("rag.services.llm_clients.openai") as mock_openai:
        mock_openai.AsyncOpenAI.return_value = mock_client
        await call_llm(
            provider="deepseek",
            model="deepseek-v4-flash",
            api_key="k",
            base_url="https://proxy.local/v1",
            system_prompt="s",
            messages=[{"role": "user", "content": "hello"}],
        )
    mock_openai.AsyncOpenAI.assert_called_once_with(
        api_key="k", base_url="https://proxy.local/v1"
    )
