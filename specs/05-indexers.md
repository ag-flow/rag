# RAG Service — Indexeurs et Providers

## Principe

Chaque workspace est associé à un **indexeur fixe** — provider + modèle. La dimension des vecteurs est déterminée à la création du workspace et ne peut pas changer sans réindexation complète.

---

## Providers supportés

### OpenAI

```json
{
  "provider": "openai",
  "model": "text-embedding-3-small",
  "api_key_ref": "openai_embedding_key"
}
```

| Modèle | Dimension | Usage recommandé |
|---|---|---|
| text-embedding-3-small | 1536 | Usage général, bon rapport qualité/coût |
| text-embedding-3-large | 3072 | Précision maximale |

---

### Voyage AI

```json
{
  "provider": "voyage",
  "model": "voyage-3",
  "api_key_ref": "voyage_api_key"
}
```

---

### Azure OpenAI

```json
{
  "provider": "azure-openai",
  "model": "text-embedding-3-small",
  "base_url": "https://{resource-name}.openai.azure.com/",
  "deployment_name": "text-embedding-3-small",
  "api_key_ref": "azure_openai_api_key"
}
```

| Modèle | Dimension | Usage recommandé |
|---|---|---|
| text-embedding-3-small | 1536 | Usage général, données dans l'écosystème Azure |
| text-embedding-3-large | 3072 | Précision maximale, données dans l'écosystème Azure |
| text-embedding-ada-002 | 1536 | Modèle legacy, compatibilité |

Recommandé pour les workspaces contenant des données internes (colis21, Pickup/DOSI) — les données restent dans l'infrastructure Azure sans transiter vers OpenAI en direct.

Le `deployment_name` est le nom donné au modèle lors de son instanciation dans le portail Azure — il peut différer du nom du modèle.

| Modèle | Dimension | Usage recommandé |
|---|---|---|
| voyage-3 | 1024 | Meilleure qualité RAG, spécialisé retrieval |
| voyage-code-3 | 1024 | Corpus code source |

Voyage AI est recommandé pour les workspaces contenant principalement du code (ag-flow-docker, colis21).

---

### Azure AI Foundry

```json
{
  "service": "voyage",
  "provider": "azure-foundry",
  "model": "voyage-4",
  "base_url": "https://{name}.{region}.models.ai.azure.com/v1",
  "api_key_ref": "azure_foundry_api_key"
}
```

| Modèle | Dimension | Service | Usage recommandé |
|---|---|---|---|
| voyage-3.5 | 1024 | voyage | Embeddings Voyage dans l'infra Azure |
| voyage-4 | 1024 | voyage | Meilleure qualité Voyage dans l'infra Azure |
| voyage-4-lite | 512 | voyage | Léger, données sensibles dans Azure |

Azure AI Foundry expose une API compatible OpenAI (`Authorization: Bearer`). Le `base_url` est l'endpoint complet du déploiement serverless Azure.

**Différence avec `azure-openai`** : azure-foundry utilise Bearer (pas `api-key`), envoie le champ `model` dans le payload, et ne nécessite pas de `api-version` dans l'URL.

---

### Ollama (pve2 homelab)

```json
{
  "provider": "ollama",
  "model": "qwen2.5-coder:14b",
  "base_url": "http://192.168.10.80:11434",
  "api_key_ref": null
}
```

| Modèle | Dimension | Usage recommandé |
|---|---|---|
| qwen2.5-coder:14b | 4096 | Code, zéro coût, données sensibles |
| nomic-embed-text | 768 | Texte général, léger |

Ollama est recommandé pour les workspaces contenant des données sensibles (colis21, pickup) — zéro donnée envoyée à l'extérieur.

---

## Table de référence des dimensions

| Provider | Modèle | Dimension |
|---|---|---|
| openai | text-embedding-3-small | 1536 |
| openai | text-embedding-3-large | 3072 |
| voyage | voyage-3 | 1024 |
| voyage | voyage-code-3 | 1024 |
| azure-openai | text-embedding-3-small | 1536 |
| azure-openai | text-embedding-3-large | 3072 |
| azure-openai | text-embedding-ada-002 | 1536 |
| azure-foundry | voyage-3.5 | 1024 |
| azure-foundry | voyage-4 | 1024 |
| azure-foundry | voyage-4-lite | 512 |
| ollama | qwen2.5-coder:14b | 4096 |
| ollama | nomic-embed-text | 768 |

La dimension est résolue automatiquement par le service à la création du workspace. Elle est stockée dans `indexer_configs.dimension` et utilisée pour créer le schéma pgvector.

---

## Règle de changement d'indexeur

Un changement de provider ou de modèle sur un workspace existant est bloqué si des vecteurs existent :

```
PATCH /workspaces/harpocrate
{ "indexer": { "provider": "voyage", "model": "voyage-3" } }

→ 409 Conflict
{
  "error": "indexer_change_requires_reindex",
  "current": "openai/text-embedding-3-small (dim=1536)",
  "requested": "voyage/voyage-3 (dim=1024)",
  "documents_count": 61,
  "action": "POST /workspaces/harpocrate/reindex?confirm=true"
}
```

Avec `?confirm=true` :
1. Supprime tous les vecteurs existants
2. Recrée la table pgvector avec la nouvelle dimension
3. Lance une réindexation complète du corpus
4. Invalide tous les hashes (force re-embed de tous les documents)

---

## Recommandations par workspace

| Workspace | Provider recommandé | Raison |
|---|---|---|
| harpocrate | openai/text-embedding-3-small | Doc Markdown, bon rapport qualité/coût |
| ag-flow-docker | voyage/voyage-code-3 | Corpus mixte code + doc |
| ag-flow-workflow | voyage/voyage-code-3 | Idem |
| colis21 | azure-openai/text-embedding-3-small | Données Pickup — restent dans l'infra Azure |