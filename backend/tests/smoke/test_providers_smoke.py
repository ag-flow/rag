"""Tests smoke opt-in pour les 3 providers réels.

Skippés par défaut (`addopts = "-m 'not smoke'"` dans pyproject.toml).
Pour les exécuter :

    $env:OPENAI_API_KEY_TEST = "sk-..."
    $env:VOYAGE_API_KEY_TEST = "vk-..."
    $env:OLLAMA_TEST_URL     = "http://192.168.10.80:11434"
    uv run pytest -m smoke -v

Chaque test skip individuellement si sa variable d'env n'est pas définie.
"""

from __future__ import annotations

import os

import pytest

from rag.indexer.providers.ollama import OllamaProvider
from rag.indexer.providers.openai import OpenAIProvider
from rag.indexer.providers.voyage import VoyageProvider


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_openai_real_returns_1536_dim() -> None:
    api_key = os.environ.get("OPENAI_API_KEY_TEST")
    if not api_key:
        pytest.skip("OPENAI_API_KEY_TEST not set")
    provider = OpenAIProvider(model="text-embedding-3-small", api_key=api_key)
    result = await provider.embed_texts(["hello", "world"])
    assert len(result) == 2
    assert len(result[0]) == 1536


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_voyage_real_returns_1024_dim() -> None:
    api_key = os.environ.get("VOYAGE_API_KEY_TEST")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY_TEST not set")
    provider = VoyageProvider(model="voyage-3", api_key=api_key)
    result = await provider.embed_texts(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 1024


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_ollama_real_returns_dim() -> None:
    base_url = os.environ.get("OLLAMA_TEST_URL")
    if not base_url:
        pytest.skip("OLLAMA_TEST_URL not set")
    provider = OllamaProvider(model="nomic-embed-text", base_url=base_url)
    result = await provider.embed_texts(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 768
