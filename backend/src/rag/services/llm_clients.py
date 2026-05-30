from __future__ import annotations

from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]


_SYSTEM_TEMPLATE = """\
Tu es un assistant expert. Réponds en te basant uniquement sur le contexte fourni.
Si la réponse n'est pas dans le contexte, dis-le explicitement.

[Contexte RAG]
---
{context}
---
"""

_SYSTEM_NO_CONTEXT = """\
Tu es un assistant expert. Aucun contexte pertinent n'a été trouvé dans le corpus.
Dis-le explicitement à l'utilisateur.
"""


def build_prompt(
    *,
    chunks: list[dict[str, Any]],
    history: list[dict[str, str]],
    message: str,
) -> tuple[str, list[dict[str, str]]]:
    """Construit le system prompt + la liste de messages pour le LLM."""
    if chunks:
        context_parts = [
            f"[chunk — path: {c['path']}]\n{c['content']}"
            for c in chunks
        ]
        system = _SYSTEM_TEMPLATE.format(context="\n\n".join(context_parts))
    else:
        system = _SYSTEM_NO_CONTEXT

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message})
    return system, messages


async def call_llm(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Appelle le LLM et retourne {answer, usage: {prompt_tokens, completion_tokens}}."""
    if provider == "claude":
        return await _call_claude(
            model=model, api_key=api_key, system=system_prompt, messages=messages
        )
    if provider == "openai":
        return await _call_openai(
            model=model, api_key=api_key, system=system_prompt, messages=messages
        )
    if provider == "azure-openai":
        return await _call_azure_openai(
            model=model, api_key=api_key, base_url=base_url, system=system_prompt, messages=messages
        )
    if provider == "ollama":
        return await _call_ollama(
            model=model, base_url=base_url or "http://localhost:11434",
            system=system_prompt, messages=messages,
        )
    raise ValueError(f"Unsupported LLM provider: {provider!r}")


async def _call_claude(
    *, model: str, api_key: str | None, system: str, messages: list[dict[str, str]]
) -> dict[str, Any]:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model, max_tokens=2000, system=system, messages=messages
    )
    return {
        "answer": response.content[0].text,
        "usage": {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        },
    }


async def _call_openai(
    *, model: str, api_key: str | None, system: str, messages: list[dict[str, str]]
) -> dict[str, Any]:
    client = openai.AsyncOpenAI(api_key=api_key)
    full_messages = [{"role": "system", "content": system}, *messages]
    response = await client.chat.completions.create(model=model, messages=full_messages)
    return {
        "answer": response.choices[0].message.content or "",
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        },
    }


async def _call_azure_openai(
    *, model: str, api_key: str | None, base_url: str | None,
    system: str, messages: list[dict[str, str]]
) -> dict[str, Any]:
    client = openai.AsyncAzureOpenAI(
        api_key=api_key,
        azure_endpoint=base_url or "",
        api_version="2024-02-01",
    )
    full_messages = [{"role": "system", "content": system}, *messages]
    response = await client.chat.completions.create(model=model, messages=full_messages)
    return {
        "answer": response.choices[0].message.content or "",
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        },
    }


async def _call_ollama(
    *, model: str, base_url: str, system: str, messages: list[dict[str, str]]
) -> dict[str, Any]:
    full_messages = [{"role": "system", "content": system}, *messages]
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={"model": model, "messages": full_messages, "stream": False},
        )
        response.raise_for_status()
        data = response.json()
    return {
        "answer": data["message"]["content"],
        "usage": {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        },
    }
