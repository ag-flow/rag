# Architecture Service/Platform — Providers d'Embedding

**Date** : 2026-06-04
**Scope** : Restructuration de `backend/src/rag/indexer/providers/` + ajout Azure AI Foundry

---

## Objectif

Séparer clairement deux responsabilités aujourd'hui mélangées dans chaque provider :

- **Service** : la capacité IA — quel payload construire, comment parser la réponse, batch_size
- **Platform** : le canal d'accès — quelle URL, quel header d'authentification

Cela permet d'accéder au même service (ex : Voyage AI) via plusieurs plateformes (direct, Azure AI Foundry) sans duplication de code.

---

## Schéma conceptuel

```
workspace config:
  { service="voyage", provider="azure-foundry", model="voyage-4", base_url=..., api_key=... }
                           ↓                            ↓
             VoyageService(model)          BearerPlatform(base_url, api_key)
                           ↓                            ↓
                  EmbeddingProviderAdapter(service, platform)
                                   ↓
                     implements EmbeddingProvider protocol
```

---

## Nouvelle structure de fichiers

```
backend/src/rag/indexer/providers/
├── protocol.py                  # inchangé — EmbeddingProvider + erreurs
├── services/
│   ├── protocol.py              # EmbeddingService protocol
│   ├── openai_compatible.py     # payload {model, input} → data[{index, embedding}]
│   ├── voyage.py                # étend openai_compatible + input_type document/query
│   ├── azure_openai.py          # étend openai_compatible, supprime model du payload
│   └── ollama.py                # API custom /api/embed, mono-input, réponse {embeddings}
├── platforms/
│   ├── protocol.py              # EmbeddingPlatform protocol
│   ├── bearer.py                # BearerPlatform(base_url, api_key)
│   ├── azure_openai.py          # AzureOpenAIPlatform — header api-key, ?api-version
│   └── ollama.py                # OllamaPlatform — no auth
├── adapter.py                   # EmbeddingProviderAdapter(service, platform, model)
└── factory.py                   # make_provider(service, provider, model, api_key, base_url)
```

Les anciens fichiers provider (`openai.py`, `voyage.py`, `azure_openai.py`, `ollama.py`, `mistral.py`, `jina.py`, `gemini.py`, `dashscope.py`) sont supprimés une fois tous les tests verts.

---

## Protocols

### EmbeddingService

```python
# services/protocol.py
class EmbeddingService(Protocol):
    batch_size: int

    def build_document_payload(self, texts: list[str], model: str) -> dict: ...
    def build_query_payload(self, text: str, model: str) -> dict: ...
    def parse_response(self, data: dict) -> list[list[float]]: ...
```

### EmbeddingPlatform

```python
# platforms/protocol.py
class EmbeddingPlatform(Protocol):
    def auth_headers(self) -> dict[str, str]: ...
    def url(self, path: str) -> str: ...
    def modify_payload(self, payload: dict) -> dict: ...  # défaut : identité
    def validate_auth(self) -> None: ...
```

---

## Services

| Classe | Fichier | Payload envoyé | input_type | batch |
|---|---|---|---|---|
| `OpenAICompatibleService` | `services/openai_compatible.py` | `{model, input}` | non | 100 |
| `VoyageService` | `services/voyage.py` | `{model, input, input_type}` | oui (doc/query) | 128 |
| `AzureOpenAIService` | `services/azure_openai.py` | `{input}` (pas de model) | non | 100 |
| `OllamaService` | `services/ollama.py` | `{model, input: str}` | non | 1 |

`VoyageService` et `AzureOpenAIService` héritent de `OpenAICompatibleService` et surchargent uniquement `build_document_payload` / `build_query_payload`.

---

## Platforms

| Classe | Fichier | Header auth | URL produite |
|---|---|---|---|
| `BearerPlatform(base_url, api_key)` | `platforms/bearer.py` | `Authorization: Bearer {key}` | `{base_url}{path}` |
| `AzureOpenAIPlatform(base_url, api_key)` | `platforms/azure_openai.py` | `api-key: {key}` | `{base_url}{path}?api-version=2024-02-01` |
| `OllamaPlatform(base_url)` | `platforms/ollama.py` | aucun | `{base_url}/api/embed` |

**Azure AI Foundry = `BearerPlatform(user_base_url, api_key)`** — pas de classe dédiée. L'utilisateur configure `base_url` vers son endpoint de déploiement serverless.

---

## Adapter

`EmbeddingProviderAdapter` est la seule classe qui implémente le protocole `EmbeddingProvider`. Elle orchestre :

1. `platform.validate_auth()` — lève `EmbeddingAuthError` si token absent
2. Découpe en batches de `service.batch_size`
3. Pour chaque batch : `platform.url("/embeddings")` + `platform.auth_headers()` + `platform.modify_payload(service.build_document_payload(...))`
4. HTTP retry 1x sur 429 / 503 / timeout (sleep paramétrable pour les tests)
5. Error mapping : 401/403 → `EmbeddingAuthError`, 429 → `EmbeddingRateLimited`, réseau/503 → `EmbeddingProviderUnreachable`
6. `service.parse_response(data)`

`embed_query()` suit le même chemin mais appelle `service.build_query_payload()` (Voyage utilisera `input_type="query"`).

---

## Factory

```python
_DIRECT_URLS: dict[str, str] = {
    "openai":    "https://api.openai.com/v1",
    "voyage":    "https://api.voyageai.com/v1",
    "mistral":   "https://api.mistral.ai/v1",
    "jina":      "https://api.jina.ai/v1",
    "gemini":    "https://generativelanguage.googleapis.com/v1beta/openai",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

def make_provider(
    *,
    service: str,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> EmbeddingProvider:
    svc  = _make_service(service)
    plat = _make_platform(provider, api_key=api_key, base_url=base_url)
    return EmbeddingProviderAdapter(service=svc, platform=plat, model=model)
```

Mapping complet service + provider → classes concrètes :

| service | provider | Service class | Platform class |
|---|---|---|---|
| `openai` | `openai` | `OpenAICompatibleService` | `BearerPlatform(DIRECT_URLS["openai"], key)` |
| `openai` | `azure-openai` | `AzureOpenAIService` | `AzureOpenAIPlatform(base_url, key)` |
| `openai` | `azure-foundry` | `OpenAICompatibleService` | `BearerPlatform(base_url, key)` |
| `voyage` | `voyage` | `VoyageService` | `BearerPlatform(DIRECT_URLS["voyage"], key)` |
| `voyage` | `azure-foundry` | `VoyageService` | `BearerPlatform(base_url, key)` |
| `mistral` | `mistral` | `OpenAICompatibleService` | `BearerPlatform(DIRECT_URLS["mistral"], key)` |
| `jina` | `jina` | `OpenAICompatibleService` | `BearerPlatform(DIRECT_URLS["jina"], key)` |
| `gemini` | `gemini` | `OpenAICompatibleService` | `BearerPlatform(DIRECT_URLS["gemini"], key)` |
| `dashscope` | `dashscope` | `OpenAICompatibleService` | `BearerPlatform(DIRECT_URLS["dashscope"], key)` |
| `ollama` | `ollama` | `OllamaService` | `OllamaPlatform(base_url)` |

---

## Changements DB

### Migration 037 — colonne `service` dans `model_dimensions`

```sql
ALTER TABLE model_dimensions ADD COLUMN service TEXT NOT NULL DEFAULT '';

UPDATE model_dimensions SET service = provider
    WHERE provider IN ('openai','voyage','mistral','jina','gemini','ollama','dashscope');

UPDATE model_dimensions SET service = 'openai'
    WHERE provider = 'azure-openai';
```

### Migration 038 — modèles Azure AI Foundry (embeddings)

```sql
INSERT INTO model_dimensions (provider, model, dimension, service) VALUES
    ('azure-foundry', 'voyage-3.5',    1024, 'voyage'),
    ('azure-foundry', 'voyage-4',      1024, 'voyage'),
    ('azure-foundry', 'voyage-4-lite',  512, 'voyage')
ON CONFLICT DO NOTHING;
```

---

## LLM — llm_clients.py

Ajout du cas `azure-foundry` dans `call_llm()` :

```python
if provider == "azure-foundry":
    return await _call_azure_foundry(
        model=model, api_key=api_key, base_url=base_url,
        system=system_prompt, messages=messages,
    )

async def _call_azure_foundry(*, model, api_key, base_url, system, messages):
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
```

---

## Tests à écrire (TDD)

| Fichier test | Ce qu'il couvre |
|---|---|
| `test_service_openai_compatible.py` | payload, parse, batch_size |
| `test_service_voyage.py` | input_type document vs query |
| `test_service_azure_openai.py` | absence du champ model dans le payload |
| `test_service_ollama.py` | format mono-input, parse {embeddings} |
| `test_platform_bearer.py` | auth_headers, url() |
| `test_platform_azure_openai.py` | header api-key, url avec api-version |
| `test_adapter.py` | batching, retry 429/503/timeout, error mapping |
| `test_provider_factory.py` | mis à jour — toutes les combinaisons service+provider |

---

## Fichiers modifiés / supprimés

**Créés** : `services/__init__.py`, `services/protocol.py`, `services/openai_compatible.py`, `services/voyage.py`, `services/azure_openai.py`, `services/ollama.py`, `platforms/__init__.py`, `platforms/protocol.py`, `platforms/bearer.py`, `platforms/azure_openai.py`, `platforms/ollama.py`, `adapter.py`

**Réécrits** : `factory.py`

**Supprimés** (après migration) : `openai.py`, `voyage.py`, `azure_openai.py`, `ollama.py`, `mistral.py`, `jina.py`, `gemini.py`, `dashscope.py`

**Migrations** : `037_add_service_to_model_dimensions.sql`, `038_embedding_models_azure_foundry.sql`

**llm_clients.py** : ajout cas `azure-foundry`

**specs/05-indexers.md** : mise à jour documentation provider
