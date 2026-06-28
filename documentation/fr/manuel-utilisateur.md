# Manuel utilisateur — ag-flow.rag

**ag-flow.rag** est une plateforme RAG (Retrieval-Augmented Generation) d'infrastructure. Elle surveille des dépôts git, indexe leur contenu en base vectorielle, et expose une interface de recherche sémantique pour les agents IA.

---

## Table des matières

1. [Concepts fondamentaux](#1-concepts-fondamentaux)
2. [Connexion et authentification](#2-connexion-et-authentification)
3. [Gestion des workspaces](#3-gestion-des-workspaces)
4. [Gestion des secrets (Harpocrate)](#4-gestion-des-secrets-harpocrate)
5. [Sources git](#5-sources-git)
6. [Indexation à la demande (push)](#6-indexation-à-la-demande-push)
7. [Recherche sémantique (MCP)](#7-recherche-sémantique-mcp)
8. [Stratégies de chunking](#8-stratégies-de-chunking)
9. [Réindexation manuelle](#9-réindexation-manuelle)
10. [Webhooks de notification](#10-webhooks-de-notification)
11. [Circuit breaker](#11-circuit-breaker)
12. [Clés API workspace](#12-clés-api-workspace)
13. [Suivi des jobs](#13-suivi-des-jobs)
14. [Playground (chat RAG)](#14-playground-chat-rag)
15. [Enrichissement LLM](#15-enrichissement-llm)
16. [Référence des providers d'embedding](#16-référence-des-providers-dembedding)

**Annexes techniques**

- [Pipeline de chunking — fonctionnement interne](./annexe-technique-chunking.md)

---

## 1. Concepts fondamentaux

### Workspace

Un workspace est un corpus isolé. Il possède :
- Sa propre base vectorielle (pgvector)
- Un provider d'embedding dédié
- Des sources git surveillées
- Des clés API d'accès

Plusieurs workspaces peuvent coexister sur la même instance. Ils sont complètement étanches l'un de l'autre.

### Job d'indexation

Toute opération d'indexation (sync git, push manuel, réindexation) crée un **job** asynchrone. Le job passe par les états : `pending` → `running` → `done` | `error` | `skipped`.

Les jobs sont traçables via l'IHM ou l'API admin.

### Déduplication par hash

Avant d'embedder un document, le système calcule son SHA-256. Si le hash est identique à la version précédemment indexée, le document est **skippé** sans consommer de crédit embedding. Seuls les fichiers réellement modifiés sont réindexés.

### Secret Harpocrate

Aucun secret (clé API provider, token git, mot de passe) n'est stocké en clair. Toutes les valeurs sensibles sont référencées par une **clé logique** (ex : `openai_embedding_key`) résolue à l'exécution depuis un coffre Harpocrate.

---

## 2. Connexion et authentification

### Accès à l'IHM

Ouvrir `https://<votre-domaine>/ui` dans un navigateur.

Deux méthodes de connexion peuvent être disponibles :

| Méthode | Quand | Rôles |
|---|---|---|
| **Compte local bootstrap** | Avant configuration OIDC | `admin` |
| **OIDC (Keycloak)** | Après configuration OIDC | `rag-admin`, `rag-viewer` |

La méthode disponible est exposée par `GET /api/auth/methods`.

### Connexion avec le compte bootstrap

Le compte bootstrap est un compte d'urgence créé au premier démarrage. Il permet d'accéder à l'IHM avant que Keycloak soit configuré.

Identifiants définis dans `.env` :
- `RAG_BOOTSTRAP_ADMIN_USERNAME` (défaut : `admin`)
- Mot de passe : la valeur claire correspondant au hash `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH`

### Configurer OIDC (Keycloak)

Une fois connecté avec le compte bootstrap, aller dans **Paramètres → Authentification OIDC** ou appeler l'API :

```http
POST /api/admin/oidc
Authorization: Bearer <RAG_MASTER_KEY>
Content-Type: application/json

{
  "issuer_url": "https://keycloak.example.com/realms/myrealm",
  "client_id": "rag",
  "client_secret_ref": "keycloak_rag_client_secret"
}
```

Les rôles requis dans Keycloak :
- `rag-admin` : accès complet lecture + écriture
- `rag-viewer` : accès lecture seule (Playground uniquement)

### Désactiver le compte bootstrap

Après avoir configuré et testé OIDC, vider `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` dans `.env` et redémarrer le backend. Le compte local n'est plus actif.

### Authentification API

| Ressource | Header attendu | Valeur |
|---|---|---|
| `/api/admin/*` | `Authorization: Bearer` | `RAG_MASTER_KEY` |
| `/workspaces/{name}/index` | `Authorization: Bearer` | clé API du workspace |
| `/mcp` | `Authorization: Bearer` | clé API du workspace |

---

## 3. Gestion des workspaces

### Créer un workspace

```http
POST /api/admin/workspaces
Authorization: Bearer <RAG_MASTER_KEY>

{
  "name": "mon-projet",
  "api_key_vault": "rag",
  "indexer": {
    "provider": "openai",
    "model": "text-embedding-3-small",
    "api_key_ref": "openai_embedding_key"
  }
}
```

Le champ `name` doit être unique, en minuscules, sans espace. Il est utilisé dans toutes les URLs.

La réponse `201 Created` contient l'`id` du workspace.

### Récupérer la clé API

```http
GET /api/admin/workspaces/{name}/apikey
Authorization: Bearer <RAG_MASTER_KEY>
```

```json
{ "api_key": "ws_xxx..." }
```

Cette clé est utilisée pour authentifier les appels `/workspaces/{name}/index` et `/mcp`.

### Lister les workspaces

```http
GET /api/admin/workspaces
Authorization: Bearer <RAG_MASTER_KEY>
```

### Modifier un workspace

```http
PATCH /api/admin/workspaces/{name}
Authorization: Bearer <RAG_MASTER_KEY>

{
  "indexer": {
    "provider": "voyage",
    "model": "voyage-3",
    "api_key_ref": "voyage_api_key"
  }
}
```

> **Attention** : changer d'indexeur quand des documents sont déjà indexés est bloqué (`409 Conflict`) et nécessite une confirmation explicite (`?confirm=true`) suivie d'une réindexation complète.

### Supprimer un workspace

```http
DELETE /api/admin/workspaces/{name}
Authorization: Bearer <RAG_MASTER_KEY>
```

Supprime le workspace, sa base vectorielle, et tous ses jobs. Irréversible.

---

## 4. Gestion des secrets (Harpocrate)

Harpocrate est le gestionnaire de secrets intégré. Aucun secret n'est stocké en clair en base de données.

### Créer un coffre

```http
POST /api/admin/harpocrate-vaults
Authorization: Bearer <RAG_MASTER_KEY>

{
  "name": "rag",
  "base_url": "https://harpocrate.example.com",
  "api_key": "harp_xxx..."
}
```

### Ajouter une clé API provider (OpenAI, Voyage, etc.)

```http
POST /api/admin/harpocrate-vaults/{vault_id}/provider-keys
Authorization: Bearer <RAG_MASTER_KEY>

{
  "logical_name": "openai_embedding_key",
  "provider": "openai",
  "value": "sk-xxx..."
}
```

La `logical_name` (`openai_embedding_key`) est la référence utilisée dans la config des workspaces et des sources.

### Ajouter un credential git (HTTPS)

```http
POST /api/admin/harpocrate-vaults/{vault_id}/git-credentials
Authorization: Bearer <RAG_MASTER_KEY>

{
  "logical_name": "github_token",
  "host": "github.com",
  "username": "mon-compte",
  "token": "ghp_xxx..."
}
```

### Importer une clé SSH

```http
POST /api/admin/harpocrate-vaults/{vault_id}/ssh-keys/import
Authorization: Bearer <RAG_MASTER_KEY>

{
  "logical_name": "github_ssh_key",
  "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n..."
}
```

### Générer une clé SSH

```http
POST /api/admin/harpocrate-vaults/{vault_id}/ssh-keys/generate
Authorization: Bearer <RAG_MASTER_KEY>

{
  "logical_name": "deploy_key",
  "comment": "rag-deploy@example.com"
}
```

La réponse contient la **clé publique** à déposer sur GitHub/GitLab comme deploy key. La clé privée est stockée dans Harpocrate et n'est jamais exposée.

---

## 5. Sources git

Une source git est un dépôt surveillé. Le worker vérifie régulièrement les nouveaux commits et réindexe les fichiers modifiés.

### Ajouter une source (HTTPS + token)

```http
POST /api/admin/workspaces/{name}/sources
Authorization: Bearer <RAG_MASTER_KEY>

{
  "name": "docs-repo",
  "type": "git",
  "config": {
    "url": "https://github.com/org/repo",
    "branch": "main",
    "auth_ref": "github_token",
    "include": ["**/*.md", "**/*.rst"],
    "exclude": ["**/node_modules/**"],
    "sync_interval_seconds": 300
  }
}
```

### Ajouter une source (SSH)

```http
POST /api/admin/workspaces/{name}/sources
Authorization: Bearer <RAG_MASTER_KEY>

{
  "name": "private-repo",
  "type": "git",
  "config": {
    "url": "git@github.com:org/repo.git",
    "branch": "main",
    "auth_ref": "github_ssh_key"
  }
}
```

### Paramètres de configuration d'une source

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `url` | string | — | URL du dépôt (HTTPS ou SSH) |
| `branch` | string | `main` | Branche à surveiller |
| `auth_ref` | string | — | Clé logique du credential Harpocrate |
| `include` | glob[] | `["**/*"]` | Patterns de fichiers à indexer |
| `exclude` | glob[] | `[]` | Patterns à exclure |
| `sync_interval_seconds` | int | 300 | Intervalle entre deux syncs (min 60) |

### Tester la connexion

```http
POST /api/admin/workspaces/{name}/sources/{source_id}/test-connection
Authorization: Bearer <RAG_MASTER_KEY>
```

Retourne `200 OK` si le dépôt est accessible, `422` avec le message d'erreur sinon.

### Forcer une synchronisation immédiate

```http
POST /api/admin/workspaces/{name}/sources/{source_id}/sync
Authorization: Bearer <RAG_MASTER_KEY>
```

Retourne `202 Accepted` avec le `job_id`. La synchronisation s'exécute en arrière-plan.

### Webhooks git (déclenchement immédiat)

Plutôt que d'attendre le polling, configurer un webhook sur GitHub/GitLab pour déclencher la synchronisation à chaque push.

**Activer le webhook sur la source :**

```http
POST /api/admin/workspaces/{name}/sources/{source_name}/webhook/enable
Authorization: Bearer <RAG_MASTER_KEY>
```

Retourne le secret HMAC à configurer dans GitHub/GitLab.

**URL du webhook à configurer dans GitHub :**

```
https://rag.example.com/api/webhooks/git/{workspace_name}/{source_name}
```

**Rotation du secret :**

```http
POST /api/admin/workspaces/{name}/sources/{source_name}/webhook/rotate-secret
Authorization: Bearer <RAG_MASTER_KEY>
```

---

## 6. Indexation à la demande (push)

L'API push permet à un service externe de demander l'indexation d'un document sans passer par une source git.

### Indexer un document

```http
POST /workspaces/{name}/index
Authorization: Bearer <clé-api-workspace>
Content-Type: application/json

{
  "path": "docs/architecture.md",
  "content": "# Architecture\n\nLe système est composé de...",
  "title": "Architecture système",
  "strategy": "replace"
}
```

| Champ | Type | Requis | Description |
|---|---|---|---|
| `path` | string | Oui | Identifiant unique du document (chemin virtuel) |
| `content` | string | Oui | Contenu brut (max 5 Mo UTF-8) |
| `title` | string | Non | Titre du document (max 512 chars) |
| `strategy` | string | Non | `replace` ou `append` (défaut : config workspace) |

**Réponse :**

```http
HTTP/1.1 202 Accepted
X-Correlation-ID: 7f3a1b2c-...

{
  "job_id": "a1b2c3d4-...",
  "status": "pending"
}
```

Le document est traité en arrière-plan. Utiliser le `job_id` pour suivre l'avancement.

### Supprimer un document indexé

```http
DELETE /workspaces/{name}/index/docs/architecture.md
Authorization: Bearer <clé-api-workspace>
```

Le chemin est encodé directement dans l'URL. La suppression est asynchrone (`202 Accepted`).

### Suivre un job push

```http
GET /api/admin/workspaces/{name}/jobs
Authorization: Bearer <RAG_MASTER_KEY>
```

Ou via WebSocket pour le streaming en temps réel :

```
WS wss://rag.example.com/ws/jobs/{job_id}/logs
```

---

## 7. Recherche sémantique (MCP)

L'endpoint MCP permet aux agents IA (Claude Code, aider, etc.) de faire des recherches sémantiques dans un ou plusieurs workspaces.

### Requête de recherche

```http
POST /mcp
Authorization: Bearer <clé-api-workspace>
Content-Type: application/json

{
  "query": "comment configurer le retry après une erreur réseau ?",
  "top_k": 5,
  "min_score": 0.7
}
```

### Recherche multi-workspace

```http
POST /mcp
Content-Type: application/json

{
  "workspaces": [
    { "name": "backend-docs", "api_key": "ws_aaa..." },
    { "name": "infra-docs",   "api_key": "ws_bbb..." }
  ],
  "query": "configuration Caddy avec Cloudflare Tunnel",
  "top_k": 10,
  "min_score": 0.6
}
```

### Réponse

```json
{
  "query": "configuration Caddy avec Cloudflare Tunnel",
  "results": [
    {
      "workspace": "infra-docs",
      "path": "docs/proxy.md",
      "title": "Reverse proxy configuration",
      "chunk_index": 3,
      "content": "Pour Cloudflare Tunnel, Caddy doit être configuré avec `auto_https off`...",
      "score": 0.92
    }
  ]
}
```

### Intégration avec Claude Code

Configurer l'endpoint MCP dans Claude Code pour utiliser la recherche RAG directement depuis le terminal.

```json
{
  "mcpServers": {
    "mon-projet-docs": {
      "url": "https://rag.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ws_xxx..."
      }
    }
  }
}
```

---

## 8. Stratégies de chunking

Le chunking contrôle comment les documents sont découpés avant l'embedding.

### Moteurs disponibles

| Moteur | Idéal pour | Description |
|---|---|---|
| `legacy` | Texte brut simple | Découpe naïve par nombre de caractères |
| `markdown` | Documentation Markdown | Respecte la hiérarchie des titres H1/H2/H3 |
| `structured` | JSON, YAML, code | Découpe intelligente par structure |
| `code` | Code source (tree-sitter) | Découpe par fonctions, classes, blocs |

### Configurer le chunking d'un workspace

```http
PUT /api/admin/workspaces/{name}/chunking-config
Authorization: Bearer <RAG_MASTER_KEY>

{
  "strategy": "markdown",
  "max_chars": 1024,
  "min_chars": 100,
  "overlap_chars": 50
}
```

### Changer de moteur

```http
PUT /api/admin/workspaces/{name}/chunking-config/engine
Authorization: Bearer <RAG_MASTER_KEY>

{
  "engine": "structured"
}
```

Si des documents sont déjà indexés, le changement de moteur déclenche automatiquement une réindexation complète.

### Stratégie par fichier

Chaque document peut avoir une stratégie d'upsert personnalisée :

```http
PATCH /api/admin/workspaces/{name}/index-keys/docs/guide.md/strategy
Authorization: Bearer <RAG_MASTER_KEY>

{
  "strategy": "append"
}
```

| Stratégie | Comportement |
|---|---|
| `replace` | Efface et remplace tous les chunks du document |
| `append` | Ajoute les nouveaux chunks sans toucher les anciens |

---

## 9. Réindexation manuelle

### Forcer la réindexation de tout le workspace

```http
POST /api/admin/workspaces/{name}/reindex
Authorization: Bearer <RAG_MASTER_KEY>
```

Retourne `202 Accepted`. Tous les documents sont réembeddés, même ceux dont le hash n'a pas changé.

### Lister les documents indexés

```http
GET /api/admin/workspaces/{name}/index-keys
Authorization: Bearer <RAG_MASTER_KEY>
```

```json
[
  {
    "path": "docs/architecture.md",
    "title": "Architecture système",
    "content_hash": "sha256:abc...",
    "indexer_used": "openai/text-embedding-3-small",
    "chunks": 12,
    "indexed_at": "2026-06-27T14:30:00Z",
    "strategy": "replace"
  }
]
```

### Détail d'un document (chunks)

```http
GET /api/admin/workspaces/{name}/index-keys/docs/architecture.md
Authorization: Bearer <RAG_MASTER_KEY>
```

Retourne la liste des chunks avec leur index et leur contenu.

---

## 10. Webhooks de notification

Les webhooks notifient un service externe à la fin de chaque job d'indexation.

### Créer un webhook

```http
POST /api/admin/workspaces/{name}/webhooks
Authorization: Bearer <RAG_MASTER_KEY>

{
  "name": "notify-ci",
  "url": "https://hooks.example.com/rag",
  "enabled": true
}
```

### Ajouter un header d'authentification

```http
PATCH /api/admin/workspaces/{name}/webhooks/{webhook_id}/headers/{header_id}
Authorization: Bearer <RAG_MASTER_KEY>

{
  "name": "X-Api-Key",
  "value": "secret_xxx"
}
```

La valeur peut aussi référencer un secret Harpocrate (`vault_ref`) pour ne pas stocker la valeur en clair.

### Payload envoyé

```json
{
  "event": "indexation.done",
  "workspace": "mon-projet",
  "job_id": "uuid...",
  "correlation_id": "uuid...",
  "triggered_by": "push",
  "status": "done",
  "files_changed": 3,
  "files_skipped": 45,
  "duration_ms": 1840,
  "finished_at": "2026-06-27T14:30:00Z"
}
```

Headers injectés automatiquement :
- `X-Correlation-ID` : identifiant de corrélation du job
- `X-RAG-Signature` : HMAC SHA-256 du payload (si `RAG_WEBHOOK_SECRET` est défini)

### Audit des appels

```http
GET /api/admin/workspaces/{name}/webhooks/calls
Authorization: Bearer <RAG_MASTER_KEY>
```

Retourne l'historique des appels avec statut HTTP et durée de réponse.

---

## 11. Circuit breaker

Le circuit breaker protège le système contre les défaillances du provider d'embedding.

### Fonctionnement

Quand un appel embedding échoue avec une erreur **bloquante** (quota épuisé, clé API invalide) ou après **épuisement des retries** sur erreur transitoire (rate limit, service indisponible), le circuit s'ouvre :

- Tous les jobs d'indexation du workspace sont mis en pause
- Le circuit reste ouvert pendant 1 heure (configurable)
- À expiration, le circuit se referme automatiquement et les jobs reprennent

### Consulter l'état du circuit

```http
GET /api/admin/workspaces/{name}/circuit-breaker
Authorization: Bearer <RAG_MASTER_KEY>
```

Circuit fermé (fonctionnement normal) :
```json
{ "status": "closed" }
```

Circuit ouvert :
```json
{
  "status": "open",
  "provider": "openai",
  "model": "text-embedding-3-small",
  "error_message": "Quota exhausted: HTTP 402",
  "opened_at": "2026-06-27T14:00:00Z",
  "open_until": "2026-06-27T15:00:00Z"
}
```

### Fermer manuellement le circuit

Après avoir résolu le problème (rechargé le compte, corrigé la clé API) :

```http
POST /api/admin/workspaces/{name}/circuit-breaker/close
Authorization: Bearer <RAG_MASTER_KEY>
```

Retourne `204 No Content`. Les jobs reprennent immédiatement.

### Stratégie de retry

| Type d'erreur | Comportement |
|---|---|
| Rate limit (429) | Retry avec backoff exponentiel : 30s, 60s, 120s… jusqu'à 4h |
| Service indisponible (5xx) | Idem |
| Quota épuisé (402) | Circuit ouvert immédiatement, pas de retry |
| Clé API invalide (401) | Circuit ouvert immédiatement, pas de retry |
| Après 10 retries épuisés | Circuit ouvert |

---

## 12. Clés API workspace

Chaque workspace peut avoir plusieurs clés API. Cela permet de révoquer une clé sans perturber les autres intégrations.

### Créer une nouvelle clé

```http
POST /api/admin/workspaces/{name}/api-keys
Authorization: Bearer <RAG_MASTER_KEY>

{
  "label": "integration-ci",
  "expires_at": "2027-01-01T00:00:00Z"
}
```

La clé générée n'est retournée qu'une seule fois à la création.

### Lister les clés actives

```http
GET /api/admin/workspaces/{name}/api-keys
Authorization: Bearer <RAG_MASTER_KEY>
```

### Révoquer une clé

```http
DELETE /api/admin/workspaces/{name}/api-keys/{key_id}
Authorization: Bearer <RAG_MASTER_KEY>
```

---

## 13. Suivi des jobs

### Lister les jobs d'un workspace

```http
GET /api/admin/workspaces/{name}/jobs
Authorization: Bearer <RAG_MASTER_KEY>
```

```json
[
  {
    "id": "uuid...",
    "triggered_by": "push",
    "status": "done",
    "files_changed": 3,
    "files_skipped": 58,
    "duration_ms": 1240,
    "started_at": "2026-06-27T14:29:58Z",
    "finished_at": "2026-06-27T14:30:00Z"
  }
]
```

**Valeurs de `triggered_by`** :
- `push` — indexation à la demande via API
- `delete` — suppression de document via API
- `schedule` — sync automatique d'une source git
- `webhook` — déclenché par webhook git
- `manual` — réindexation forcée via l'admin

**Valeurs de `status`** :
- `pending` — en attente d'exécution
- `running` — en cours
- `done` — succès
- `skipped` — document inchangé (hash identique)
- `error` — échec (voir `error_message`)

### Détail des fichiers traités

```http
GET /api/admin/workspaces/{name}/jobs/{job_id}/files
Authorization: Bearer <RAG_MASTER_KEY>
```

### Streaming logs en temps réel

```
WS wss://rag.example.com/ws/jobs/{job_id}/logs
```

Le WebSocket rejoue les événements passés puis envoie les nouveaux en direct. Fermeture automatique à la fin du job.

---

## 14. Playground (chat RAG)

Le Playground permet de tester la recherche RAG de manière conversationnelle depuis l'IHM.

**Accès** : `/ui` → workspace → onglet Playground

**Prérequis** :
- Être connecté avec un compte OIDC (rôle `rag-admin` ou `rag-viewer`)
- Le workspace doit avoir une LLM config configurée

### Configurer une LLM config

```http
POST /api/admin/workspaces/{name}/llm-configs
Authorization: Bearer <RAG_MASTER_KEY>

{
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "api_key_ref": "anthropic_api_key",
  "temperature": 0.2,
  "max_tokens": 2048
}
```

### Appel API direct

```http
POST /api/workspaces/{name}/playground/chat
Authorization: Bearer <session-cookie>

{
  "message": "comment fonctionne le circuit breaker ?",
  "history": [],
  "top_k": 5,
  "min_score": 0.7
}
```

---

## 15. Enrichissement LLM

L'enrichissement permet d'exécuter des prompts LLM sur les documents indexés pour générer des métadonnées supplémentaires (résumé, documentation, tags…).

### Flux d'enrichissement

1. Document indexé (chunks bruts)
2. Triggers évaluent l'extension du fichier
3. Les prompts associés s'exécutent séquentiellement
4. Les métadonnées générées sont injectées dans les chunks

### Créer un prompt template

```http
POST /api/admin/prompts
Authorization: Bearer <RAG_MASTER_KEY>

{
  "name": "generate-python-docstring",
  "language": "python",
  "metadata_key": "docstring",
  "result_type": "text",
  "prompt": "Tu es expert Python. Génère la docstring de la fonction suivante.\n\nCODE :\n{content}"
}
```

### Créer un trigger

```http
POST /api/admin/workspaces/{name}/triggers
Authorization: Bearer <RAG_MASTER_KEY>

{
  "extension": ".py",
  "enabled": true
}
```

### Associer un prompt au trigger

```http
POST /api/admin/workspaces/{name}/triggers/{trigger_id}/prompts
Authorization: Bearer <RAG_MASTER_KEY>

{
  "template_id": "uuid-du-template",
  "llm_config_id": "uuid-llm-config",
  "order_index": 1
}
```

---

## 16. Référence des providers d'embedding

| Provider | Modèle | Dimension | Notes |
|---|---|---|---|
| `openai` | `text-embedding-3-small` | 1536 | Recommandé — bon rapport qualité/coût |
| `openai` | `text-embedding-3-large` | 3072 | Meilleure précision, 2× plus cher |
| `voyage` | `voyage-3` | 1024 | Excellent pour texte général |
| `voyage` | `voyage-code-3` | 1024 | Spécialisé code source |
| `azure_openai` | `text-embedding-3-small` | 1536 | OpenAI via endpoint Azure (conformité données) |
| `azure_foundry` | `voyage-3.5` | 1024 | Voyage via Azure AI Foundry |
| `azure_foundry` | `voyage-4` | 1024 | Voyage v4 via Azure |
| `azure_foundry` | `voyage-4-lite` | 512 | Version légère, rapide |
| `ollama` | `nomic-embed-text` | 768 | Local, zéro coût, données sensibles |
| `ollama` | `qwen2.5-coder:14b` | 4096 | Local, spécialisé code |

Consulter la liste complète avec les tarifs :

```http
GET /api/admin/models/pricing
Authorization: Bearer <RAG_MASTER_KEY>
```
