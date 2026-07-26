"""Référentiel UNIQUE des masques d'URL d'appel par provider.

Chaque capacité (embeddings / chat / rerank) d'un provider est décrite par un
template — placeholders ``{base_url}`` et ``{model}`` — et une base par défaut
quand l'utilisateur n'en fournit pas. Ce référentiel est :

- exposé à l'IHM (GET /api/admin/providers/url-templates) pour afficher
  l'URL réelle d'appel sous le champ Base URL du formulaire endpoint ;
- utilisé côté indexation pour résoudre le template d'URL optionnel porté
  par un modèle du registre (model_dimensions.url_template).

Les templates reflètent le comportement RÉEL des adapters (factory embedding,
llm_clients, rerank providers) — toute évolution d'un adapter doit être
répercutée ici.
"""

from __future__ import annotations

from typing import TypedDict


class CapabilityUrl(TypedDict):
    template: str
    default_base_url: str | None


# provider -> capability -> masque. Capacités absentes = non supportées.
PROVIDER_URL_TEMPLATES: dict[str, dict[str, CapabilityUrl]] = {
    "openai": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.openai.com/v1",
        },
        "chat": {
            "template": "{base_url}/chat/completions",
            "default_base_url": "https://api.openai.com/v1",
        },
    },
    "azure-openai": {
        # base_url = racine de la ressource (https://{resource}.openai.azure.com) ;
        # le nom de déploiement = {model} (surchargez url_template sur le modèle
        # du registre si votre déploiement porte un autre nom).
        "embeddings": {
            "template": "{base_url}/openai/deployments/{model}/embeddings"
            "?api-version=2024-02-01",
            "default_base_url": None,
        },
        "chat": {
            "template": "{base_url}/openai/deployments/{model}/chat/completions"
            "?api-version=2024-02-01",
            "default_base_url": None,
        },
    },
    "azure-foundry": {
        "embeddings": {"template": "{base_url}/embeddings", "default_base_url": None},
        "chat": {"template": "{base_url}/chat/completions", "default_base_url": None},
        # L'URL rerank Azure Foundry est fournie complète par l'utilisateur.
        "rerank": {"template": "{base_url}", "default_base_url": None},
    },
    "voyage": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.voyageai.com/v1",
        },
        "rerank": {
            "template": "{base_url}/rerank",
            "default_base_url": "https://api.voyageai.com/v1",
        },
    },
    "mistral": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.mistral.ai/v1",
        },
    },
    "jina": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.jina.ai/v1",
        },
        "rerank": {
            "template": "{base_url}/rerank",
            "default_base_url": "https://api.jina.ai/v1",
        },
    },
    "gemini": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        },
        "chat": {
            "template": "{base_url}/chat/completions",
            "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        },
    },
    "dashscope": {
        # L'API embeddings DashScope native est une URL complète (pas de path).
        "embeddings": {
            "template": "{base_url}",
            "default_base_url": "https://dashscope-intl.aliyuncs.com/api/v1/services"
            "/embeddings/text-embedding/text-embedding",
        },
        "chat": {
            "template": "{base_url}/chat/completions",
            "default_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        },
        "rerank": {
            "template": "{base_url}",
            "default_base_url": "https://dashscope-intl.aliyuncs.com/api/v1/services"
            "/rerank/text-rerank/text-rerank",
        },
    },
    "ollama": {
        "embeddings": {
            "template": "{base_url}/api/embed",
            "default_base_url": "http://192.168.10.80:11434",
        },
        "chat": {
            "template": "{base_url}/api/chat",
            "default_base_url": "http://localhost:11434",
        },
        # Fork uniquement : Ollama upstream n'expose pas /api/rerank (BUG-006).
        "rerank": {"template": "{base_url}/api/rerank", "default_base_url": None},
    },
    "ollama-cloud": {
        "chat": {
            "template": "{base_url}/api/chat",
            "default_base_url": "https://ollama.com",
        },
    },
    "fireworks": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.fireworks.ai/inference/v1",
        },
        "rerank": {
            "template": "{base_url}/rerank",
            "default_base_url": "https://api.fireworks.ai/inference/v1",
        },
    },
    "deepinfra": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.deepinfra.com/v1/openai",
        },
        "rerank": {
            "template": "{base_url}/v1/inference/{model}",
            "default_base_url": "https://api.deepinfra.com",
        },
    },
    "together": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.together.xyz/v1",
        },
    },
    "cohere": {
        "embeddings": {
            "template": "{base_url}/embeddings",
            "default_base_url": "https://api.cohere.ai/compatibility/v1",
        },
        "rerank": {
            "template": "{base_url}/v2/rerank",
            "default_base_url": "https://api.cohere.com",
        },
    },
    "mixedbread": {
        "rerank": {
            "template": "{base_url}/v1/reranking",
            "default_base_url": "https://api.mixedbread.com",
        },
    },
    "claude": {
        "chat": {
            "template": "{base_url}/v1/messages",
            "default_base_url": "https://api.anthropic.com",
        },
    },
    "deepseek": {
        "chat": {
            "template": "{base_url}/chat/completions",
            "default_base_url": "https://api.deepseek.com/v1",
        },
    },
}


def resolve_url(
    *,
    provider: str,
    capability: str,
    model: str,
    base_url: str | None = None,
    template: str | None = None,
) -> str | None:
    """URL réelle d'appel pour (provider, capability, model).

    ``template`` (surcharge portée par le modèle du registre) prime sur le
    masque du provider ; ``{url}`` y est accepté comme alias de ``{base_url}``.
    Retourne None si la capacité n'est pas décrite et qu'aucune surcharge
    n'est fournie, ou si une base est requise mais absente.
    """
    entry = PROVIDER_URL_TEMPLATES.get(provider, {}).get(capability)
    tpl = (template or "").strip() or (entry["template"] if entry else None)
    if tpl is None:
        return None
    tpl = tpl.replace("{url}", "{base_url}")
    base = (base_url or "").strip() or (entry["default_base_url"] if entry else None)
    if "{base_url}" in tpl and not base:
        return None
    return tpl.format(base_url=(base or "").rstrip("/"), model=model)
