# Design — RAG Playground

**Date :** 2026-05-30
**Statut :** validé
**Jalon :** 1/2 — chat fonctionnel + config LLM par workspace

## Contexte

Interface de chat intégrée à l'IHM permettant de tester le RAG d'un workspace ou de faire des requêtes ad hoc. Historique volatile (côté client uniquement, aucune persistance). Pas de streaming. Accessible aux rôles `rag-admin` et `rag-viewer`.

---

## Base de données

### Migration 030

```sql
CREATE TABLE workspace_llm_configs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    provider     TEXT NOT NULL,
    model        TEXT NOT NULL,
    base_url     TEXT,
    api_key_ref  TEXT,
    enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, provider, model)
);
```

**Champs :**
- `provider` : `'claude' | 'openai' | 'azure-openai' | 'ollama'`
- `model` : ex: `'claude-sonnet-4-5'`, `'gpt-4o'`
- `base_url` : requis pour `azure-openai` et `ollama`, null sinon
- `api_key_ref` : `harpo_path` d'une entrée `provider_api_keys` accessible à l'utilisateur — null pour ollama local

---

## Backend

### Nouvelles dépendances

```toml
"anthropic>=0.40",
"openai>=1.50",
```

### Schémas (`schemas/playground.py`)

```
LlmConfigCreate   provider, model, base_url, api_key_ref, enabled
LlmConfigOut      id, provider, model, base_url, api_key_ref, enabled, created_at
LlmConfigPatch    enabled (bool)

PlaygroundChatRequest
    message       str
    history       list[{role: "user"|"assistant", content: str}]
    llm           {provider: str, model: str}
    top_k         int = 5
    min_score     float = 0.7

PlaygroundChatResponse
    message       str
    answer        str
    chunks        list[{path, chunk_index, content, score}]
    usage         {prompt_tokens, completion_tokens}
```

### Routes admin — LLM configs

```
GET    /workspaces/{name}/llm-configs          → list[LlmConfigOut]
POST   /workspaces/{name}/llm-configs          → LlmConfigOut  (201)
DELETE /workspaces/{name}/llm-configs/{id}     → 204
PATCH  /workspaces/{name}/llm-configs/{id}     → LlmConfigOut
```

Auth : `require_master_key_or_authenticated_admin`.

### Route chat

```
POST /workspaces/{name}/playground/chat
Auth : require_oidc_role("rag-admin") OU require_oidc_role("rag-viewer")
```

**Pipeline :**
1. Charge le workspace + indexer config
2. Embed `request.message` via l'indexer du workspace (même provider/clé)
3. `vector_search` → `top_k` chunks, filtrer par `min_score`
4. Construit le prompt :

```
[System]
Tu es un assistant expert. Réponds en te basant uniquement sur le contexte fourni.
Si la réponse n'est pas dans le contexte, dis-le explicitement.

[Contexte RAG]
---
[chunk 1 — path: {path}]
{content}
[chunk 2 — path: {path}]
{content}
---

[Historique]
User: {msg}
Assistant: {msg}
...

[Message courant]
User: {message}
```

5. Charge la `LlmConfig` correspondant à `(name, provider, model)` — 404 si absente ou disabled
6. Résout `api_key_ref` depuis Harpocrate (même pattern `_resolve_secret` de detect-branches)
7. Appelle le LLM
8. Retourne `PlaygroundChatResponse`

### Service LLM clients (`services/llm_clients.py`)

```python
async def call_llm(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    prompt: str,
    history: list[dict],
    message: str,
) -> dict:  # {answer: str, usage: {prompt_tokens, completion_tokens}}
```

Implémentations :
- **Claude** : `anthropic.AsyncAnthropic(api_key=api_key).messages.create(...)`
- **OpenAI** : `openai.AsyncOpenAI(api_key=api_key).chat.completions.create(...)`
- **Azure OpenAI** : `openai.AsyncAzureOpenAI(api_key=api_key, azure_endpoint=base_url, api_version="2024-02-01").chat.completions.create(...)`
- **Ollama** : `httpx.AsyncClient().post(f"{base_url}/api/chat", json={...})`

---

## Frontend

### Navigation

Nouvel onglet **« Playground »** dans `WorkspaceDetailPanel` (après « Rerank »).

Le Playground contient deux sous-onglets :
- **Config LLM** (rag-admin uniquement)
- **Chat** (rag-admin + rag-viewer)

### Onglet Config LLM

Tableau : provider | modèle | clé API (`key_id` du credential) | activé (toggle) | supprimer

Bouton « + Ajouter un LLM » → dialog :
1. Select provider (claude / openai / azure-openai / ollama)
2. Select modèle (liste statique par provider)
3. Select clé API → `useProviderKeysByProvider(provider)` (null/aucune pour ollama local)
4. Base URL (si azure-openai ou ollama)

Modèles par provider :
```
claude       : claude-sonnet-4-5, claude-opus-4-5
openai       : gpt-4o, gpt-4o-mini, o1
azure-openai : gpt-4o, gpt-4o-mini
ollama       : (champ libre — liste les modèles Ollama disponibles)
```

### Onglet Chat

```
[ LLM ▾ ]  top_k: [5]  min_score: [0.7]  [ 🗑 Réinitialiser ]
──────────────────────────────────────────────────────────────
  [historique scrollable]
  Chaque réponse assistant inclut :
    [▸ N chunks] — dépliable : path | score | contenu
    Tokens: prompt=X / completion=Y
──────────────────────────────────────────────────────────────
[ Votre message...                                  Envoyer ]
```

- Sélecteur LLM : uniquement les configs `enabled: true`
- Spinner pendant l'appel
- `useState<Message[]>` — historique envoyé à chaque call
- Bouton Réinitialiser vide `messages` et repart d'une session propre

### Types et hooks

```typescript
// Nouveaux types
LlmConfig, LlmConfigCreate
PlaygroundMessage, PlaygroundChatRequest, PlaygroundChatResponse

// Nouveaux hooks
useLlmConfigs(workspaceName)
useAddLlmConfig(workspaceName)
useDeleteLlmConfig(workspaceName)
usePatchLlmConfig(workspaceName)
usePlaygroundChat(workspaceName)  // useMutation
```

### i18n

Nouveau namespace `playground` (fr + en).

---

## Périmètre hors-scope (Jalon 2)

- Streaming des réponses LLM
- Historique persisté / export
- Métriques d'usage agrégées
- Écran de gestion avancée des LLM (hors workspace)
