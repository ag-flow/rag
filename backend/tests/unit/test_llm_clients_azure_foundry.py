# backend/tests/unit/test_llm_clients_azure_foundry.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.services.llm_clients import call_llm


@pytest.mark.asyncio
async def test_call_llm_azure_foundry_dispatches_to_openai_client() -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="réponse azure foundry"))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("rag.services.llm_clients.openai") as mock_openai:
        mock_openai.AsyncOpenAI.return_value = mock_client
        result = await call_llm(
            provider="azure-foundry",
            model="meta-llama-3.3-70b-instruct",
            api_key="az-key",
            base_url="https://name.region.models.ai.azure.com/v1",
            system_prompt="Tu es un assistant.",
            messages=[{"role": "user", "content": "Bonjour"}],
        )

    mock_openai.AsyncOpenAI.assert_called_once_with(
        api_key="az-key",
        base_url="https://name.region.models.ai.azure.com/v1",
    )
    assert result["answer"] == "réponse azure foundry"
    assert result["usage"]["prompt_tokens"] == 10
    assert result["usage"]["completion_tokens"] == 5


@pytest.mark.asyncio
async def test_call_llm_azure_foundry_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        await call_llm(
            provider="unknown-llm",
            model="x",
            api_key=None,
            base_url=None,
            system_prompt="",
            messages=[],
        )
