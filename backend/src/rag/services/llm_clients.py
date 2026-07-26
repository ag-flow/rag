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
    if provider in _OPENAI_COMPATIBLE_URLS:
        return await _call_openai_compatible(
            model=model,
            api_key=api_key,
            base_url=base_url or _OPENAI_COMPATIBLE_URLS[provider],
            system=system_prompt,
            messages=messages,
        )
    if provider == "azure-openai":
        return await _call_azure_openai(
            model=model, api_key=api_key, base_url=base_url, system=system_prompt, messages=messages
        )
    if provider in ("ollama", "ollama-cloud"):
        # ollama-cloud : même API que le daemon local, hébergée sur
        # https://ollama.com avec authentification Bearer par clé API.
        default_url = "https://ollama.com" if provider == "ollama-cloud" else "http://localhost:11434"
        return await _call_ollama(
            model=model, api_key=api_key, base_url=base_url or default_url,
            system=system_prompt, messages=messages,
        )
    if provider == "azure-foundry":
        return await _call_azure_foundry(
            model=model,
            api_key=api_key,
            base_url=base_url,
            system=system_prompt,
            messages=messages,
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


# Providers de chat OpenAI-compatibles : URL par défaut, surchargée par la
# base_url de la config le cas échéant.
_OPENAI_COMPATIBLE_URLS: dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "deepseek": "https://api.deepseek.com/v1",
    "dashscope": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
}


async def _call_openai_compatible(
    *,
    model: str,
    api_key: str | None,
    base_url: str,
    system: str,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    full_messages = [{"role": "system", "content": system}, *messages]
    response = await client.chat.completions.create(model=model, messages=full_messages)
    return {
        "answer": response.choices[0].message.content or "",
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
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


async def _call_azure_foundry(
    *, model: str, api_key: str | None, base_url: str | None,
    system: str, messages: list[dict[str, str]]
) -> dict[str, Any]:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
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
    *,
    model: str,
    base_url: str,
    system: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
) -> dict[str, Any]:
    full_messages = [{"role": "system", "content": system}, *messages]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={"model": model, "messages": full_messages, "stream": False},
            headers=headers,
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


# ─── Contextual retrieval « Prompt B » ────────────────────────────────────────
# Prompt caching validé sur la doc Anthropic (2026-07) avant câblage (spec §2) :
# `cache_control: ephemeral`, TTL 5 min (d'où le traitement en rafale des
# chunks d'un même document), minimum cacheable 1024 tokens (2048 sur Haiku),
# écriture du cache +25 %, lecture -90 %. Le marqueur n'est posé que si le
# préfixe document atteint le seuil — en dessous, il coûterait sans servir.
_CACHE_MIN_PREFIX_TOKENS = 2048
_CACHE_CHAR_RATIO = 4  # heuristique len/4, cohérente avec HeuristicTokenEstimator
CONTEXT_MAX_TOKENS = 120  # spec : contexte ≤ 100 tokens, marge de fin de phrase


async def call_llm_with_cached_prefix(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    cached_prefix: str,
    prompt: str,
    max_tokens: int = CONTEXT_MAX_TOKENS,
) -> str:
    """Un appel court avec un gros préfixe partagé (document complet).

    Claude : préfixe marqué `cache_control` au-delà du seuil — les appels en
    rafale sur le même document ne paient le document qu'une fois. Autres
    providers : concaténation simple (OpenAI cache automatiquement les longs
    préfixes identiques ; Ollama est local, pas de facturation).
    """
    use_anthropic_cache = (
        provider == "claude"
        and anthropic is not None
        and len(cached_prefix) // _CACHE_CHAR_RATIO >= _CACHE_MIN_PREFIX_TOKENS
    )
    if use_anthropic_cache:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": cached_prefix,
                            "cache_control": {"type": "ephemeral"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        return response.content[0].text

    result = await call_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        system_prompt="",
        messages=[{"role": "user", "content": f"{cached_prefix}\n\n{prompt}"}],
    )
    return str(result["answer"] or "")
