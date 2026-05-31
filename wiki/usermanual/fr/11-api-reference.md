# 11 — Référence API

Référence complète de tous les endpoints du service ag-flow.rag.

---

## Authentification

### Master key (API d'administration)

```http
Authorization: Bearer {RAG_MASTER_KEY}
```

Utilisée pour : `/api/admin/*`, `/api/webhooks/git/*`

### Clé API workspace

```http
Authorization: Bearer {workspace_api_key}
```

Utilisée pour : `/workspaces/{name}/index`, `/mcp` (ancien endpoint REST)

### Session OIDC

Cookie `_oidc_session` (obtenu via le flow OIDC).
Utilisée pour : `/api/workspaces/*/playground/*`

### URL MCP (nouveau)

```
URL: https://rag.votre-domaine.fr/mcp/{workspace_uuid}
Header: Authorization: Bearer {workspace_api_key}
```

---

## Health & Status

### GET /health

Vérifie que le service est en vie.

```bash
curl https://rag.votre-domaine.fr/health
```

Réponse :
```json
{"status": "healthy", "database": "connected"}
```

### GET /health/readiness

Vérifie que le service est prêt à traiter des requêtes (base de données connectée).

### GET /version

Retourne la version du service.

```json
{"version": "1.0.0", "git_sha": "abc123"}
```

---

## Authentification

### GET /auth/methods

Retourne les méthodes d'authentification disponibles (public).

```json
{
  "methods": ["oidc", "local"],
  "oidc_issuer": "https://keycloak.votre-domaine.fr/realms/homelab"
}
```

### POST /auth/login

Authentification locale (compte bootstrap).

```bash
curl -X POST https://rag.votre-domaine.fr/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "votre-mot-de-passe"}'
```

### GET /auth/me

Retourne les informations de l'utilisateur connecté (session requise).

```json
{
  "username": "admin@votre-domaine.fr",
  "roles": ["rag-admin"]
}
```

### POST /auth/logout

Termine la session courante.

---

## Administration — Workspaces

### GET /api/admin/workspaces

Liste tous les workspaces.

```bash
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  https://rag.votre-domaine.fr/api/admin/workspaces
```

### POST /api/admin/workspaces

Crée un nouveau workspace.

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "mon-projet",
    "indexer": {
      "provider": "openai",
      "model": "text-embedding-3-small",
      "api_key_ref": "openai_key"
    }
  }'
```

Réponse `201 Created` :
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "mon-projet",
  "indexer": {"provider": "openai", "model": "text-embedding-3-small"},
  "api_key": "ws_xxxxx"
}
```

### GET /api/admin/workspaces/{name}

Retourne le détail d'un workspace.

### PATCH /api/admin/workspaces/{name}

Modifie un workspace (sync_interval, etc.).

### DELETE /api/admin/workspaces/{name}

Supprime un workspace et sa base pgvector.

### GET /api/admin/workspaces/{name}/apikey

Retourne la première clé API active du workspace (idempotent).

```json
{"workspace": "mon-projet", "api_key": "ws_xxxxx"}
```

### POST /api/admin/workspaces/{name}/reindex

Force une réindexation complète du workspace.

---

## Administration — Clés API workspace

### GET /api/admin/workspaces/{name}/api-keys

Liste toutes les clés API du workspace.

```json
[
  {
    "id": "uuid...",
    "name": "agent-agflow",
    "fingerprint_preview": "a3f2c1d4",
    "status": "active",
    "created_at": "2026-05-31T10:00:00Z"
  }
]
```

### POST /api/admin/workspaces/{name}/api-keys

Crée une nouvelle clé API.

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/api-keys \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "claude-code"}'
```

Réponse `201 Created` — la clé est retournée **une seule fois** :
```json
{
  "id": "uuid...",
  "name": "claude-code",
  "api_key": "ws_xxxxx"
}
```

### POST /api/admin/workspaces/{name}/api-keys/{id}/rotate

Effectue une rotation. L'ancienne clé reste valide 72h.

```json
{
  "new_key_id": "uuid...",
  "new_api_key": "ws_yyyyy",
  "grace_until": "2026-06-02T10:00:00Z"
}
```

### DELETE /api/admin/workspaces/{name}/api-keys/{id}

Révoque immédiatement une clé.

---

## Administration — Sources git

### GET /api/admin/workspaces/{name}/sources

Liste les sources git du workspace.

### POST /api/admin/workspaces/{name}/sources

Ajoute une source git.

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/sources \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "docs",
    "type": "git",
    "git_provider": "github",
    "auth_type": "token",
    "auth_ref": "github_token",
    "config": {
      "url": "https://github.com/mon-org/mon-repo",
      "branch": "main",
      "include": ["**/*.md"]
    }
  }'
```

### POST /api/admin/workspaces/{name}/sources/{id}/test

Teste la connexion à une source.

```json
{"success": true, "message": null}
```

### PATCH /api/admin/workspaces/{name}/sources/{id}

Modifie une source.

### DELETE /api/admin/workspaces/{name}/sources/{id}

Supprime une source.

---

## Administration — Webhooks sources (entrants)

### POST /api/admin/workspaces/{name}/sources/{source}/webhook/enable

Active le mode webhook sur une source. Retourne l'URL et le secret (une seule fois).

```json
{
  "source_name": "docs",
  "webhook_url": "https://rag.votre-domaine.fr/api/webhooks/git/mon-projet/docs",
  "secret": "3f8a2c..."
}
```

### POST /api/admin/workspaces/{name}/sources/{source}/webhook/disable

Désactive le webhook. La source repasse en mode polling.

### POST /api/admin/workspaces/{name}/sources/{source}/webhook/rotate-secret

Génère un nouveau secret webhook (retourné une seule fois).

```json
{"secret": "nouveau_secret_..."}
```

---

## Administration — Webhooks sortants

### GET /api/admin/workspaces/{name}/webhooks

Liste les webhooks sortants du workspace.

### POST /api/admin/workspaces/{name}/webhooks

Crée un webhook sortant.

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "notify-agflow",
    "url": "https://agflow.votre-domaine.fr/hooks/rag",
    "enabled": true,
    "headers": [
      {"name": "X-Api-Key", "value": "secret", "vault": "coffre-principal", "enabled": true}
    ]
  }'
```

### PATCH /api/admin/workspaces/{name}/webhooks/{webhook_id}

Modifie un webhook (ex : activer/désactiver).

```bash
curl -X PATCH .../webhooks/{id} -d '{"enabled": false}'
```

### DELETE /api/admin/workspaces/{name}/webhooks/{webhook_id}

Supprime un webhook.

### GET /api/admin/workspaces/{name}/webhooks/calls

Audit log des appels webhook (dernières 24h).

Paramètres :
- `webhook_id` : filtrer sur un webhook
- `correlation_id` : filtrer sur un événement
- `status` : `success` ou `error`
- `limit` : nombre de résultats (défaut 50)

### DELETE /api/admin/workspaces/{name}/webhooks/calls

Purge manuelle du log d'audit.

---

## Administration — Jobs

### GET /api/admin/workspaces/{name}/jobs

Historique des jobs d'indexation.

```json
[
  {
    "id": "uuid...",
    "triggered_by": "git",
    "status": "done",
    "files_changed": 3,
    "files_skipped": 58,
    "duration_ms": 1240,
    "started_at": "2026-05-31T09:00:00Z",
    "finished_at": "2026-05-31T09:00:01Z"
  }
]
```

---

## Administration — Reranking

### GET /api/admin/workspaces/{name}/rerank

Retourne la configuration de reranking.

### PUT /api/admin/workspaces/{name}/rerank

Configure le reranking.

```bash
curl -X PUT https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/rerank \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "cohere",
    "model": "rerank-english-v3.0",
    "api_key_ref": "cohere_key",
    "top_k_pre_rerank": 20
  }'
```

### DELETE /api/admin/workspaces/{name}/rerank

Supprime la configuration de reranking.

---

## Administration — LLM Configs (Playground)

### GET /api/admin/workspaces/{name}/llm-configs

Liste les LLM configurés pour le Playground.

### POST /api/admin/workspaces/{name}/llm-configs

Ajoute une configuration LLM.

```bash
curl -X POST .../llm-configs \
  -d '{
    "provider": "openai",
    "model": "gpt-4o",
    "api_key_ref": "openai_key",
    "enabled": true
  }'
```

### PATCH /api/admin/workspaces/{name}/llm-configs/{id}

Modifie une configuration LLM (ex : activer/désactiver).

### DELETE /api/admin/workspaces/{name}/llm-configs/{id}

Supprime une configuration LLM.

---

## Administration — Prompts templates

### GET /api/admin/prompts

Liste tous les templates de prompts.

### POST /api/admin/prompts

Crée un template.

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/prompts \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "summarize-fr",
    "language": "fr-FR",
    "metadata_key": "summary",
    "result_type": "text",
    "prompt": "Résume ce document en français en 3 phrases.\n\nDOCUMENT :\n{content}"
  }'
```

### PATCH /api/admin/prompts/{id}

Modifie un template.

### DELETE /api/admin/prompts/{id}

Supprime un template (erreur si référencé par un trigger).

---

## Administration — Triggers

### GET /api/admin/workspaces/{name}/triggers

Liste les triggers d'enrichissement.

### POST /api/admin/workspaces/{name}/triggers

Crée un trigger.

```bash
curl -X POST .../triggers \
  -d '{"extension": ".py", "enabled": true}'
```

### POST /api/admin/workspaces/{name}/triggers/{id}/prompts

Ajoute un prompt au trigger.

```bash
curl -X POST .../triggers/{id}/prompts \
  -d '{
    "template_id": "uuid-template",
    "llm_id": "uuid-llm-config",
    "order_index": 1,
    "enabled": true
  }'
```

### DELETE /api/admin/workspaces/{name}/triggers/{id}

Supprime un trigger et tous ses prompts.

---

## Administration — Harpocrate

### GET /api/admin/harpocrate-vaults

Liste les coffres configurés.

### POST /api/admin/harpocrate-vaults

Crée un coffre.

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/harpocrate-vaults \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "coffre-principal",
    "base_url": "https://harpocrate.votre-domaine.fr",
    "api_key_id": "k-001",
    "api_key": "hrpv_1_xxx"
  }'
```

### PUT /api/admin/harpocrate-vaults/{id}

Modifie un coffre (remplace la clé API).

### DELETE /api/admin/harpocrate-vaults/{id}

Supprime un coffre.

### POST /api/admin/harpocrate-vaults/{id}/set-default

Désigne ce coffre comme coffre par défaut.

### POST /api/admin/harpocrate-vaults/{id}/test-connection

Teste la connexion au coffre.

---

## Administration — OIDC

### GET /api/admin/oidc

Retourne la configuration OIDC active.

### POST /api/admin/oidc

Configure ou met à jour l'OIDC.

```bash
curl -X POST https://rag.votre-domaine.fr/api/admin/oidc \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "issuer": "https://keycloak.votre-domaine.fr/realms/homelab",
    "client_id": "rag-service",
    "client_secret_ref": "keycloak_rag_client_secret"
  }'
```

---

## Configuration globale — Langues

### GET /config/languages

Liste les langues/cultures disponibles.

### POST /config/languages

Ajoute une culture personnalisée.

```bash
curl -X POST https://rag.votre-domaine.fr/config/languages \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"code": "vi-VN", "label": "Tiếng Việt"}'
```

### DELETE /config/languages/{code}

Supprime une culture personnalisée (pas les cultures pré-installées).

---

## API Workspace — Indexation push

### POST /workspaces/{name}/index

Indexe un document à la demande (synchrone ou asynchrone selon le mode).

```bash
curl -X POST https://rag.votre-domaine.fr/workspaces/mon-projet/index \
  -H "Authorization: Bearer $WORKSPACE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "generated/analyse.md",
    "content": "# Analyse\n\nContenu du document..."
  }'
```

Réponse si contenu inchangé :
```json
{"path": "generated/analyse.md", "status": "skipped", "reason": "content_unchanged"}
```

Réponse si indexé :
```json
{"path": "generated/analyse.md", "status": "indexed", "chunks": 4, "hash": "sha256:abc..."}
```

---

## MCP natif — Recherche sémantique

### POST /mcp/{workspace_id}

Endpoint MCP Streamable HTTP. Utilisé via le protocole MCP (pas directement via curl).

```bash
# URL : https://rag.votre-domaine.fr/mcp/{uuid-workspace}
# Header : Authorization: Bearer {workspace_api_key}
# Protocol : Model Context Protocol (JSON-RPC 2.0)
```

Outil disponible : `rag_search(query, top_k=5, min_score=0.3)`

---

## Webhooks entrants (push git)

### POST /api/webhooks/git/{workspace_name}/{source_name}

Reçoit les push events des providers git (GitHub, GitLab, Gitea, Bitbucket, Azure DevOps).

| Aspect | Détail |
|---|---|
| Auth | Signature HMAC (GitHub/Gitea/Bitbucket) ou token (GitLab) ou Basic Auth (Azure) |
| Réponse succès | `202 Accepted {"status": "pending", "job_id": "..."}` |
| Réponse branche non surveillée | `200 OK {"status": "ignored", "reason": "branch_mismatch"}` |
| Réponse source désactivée | `404 Not Found` |
| Réponse signature invalide | `401 Unauthorized` |

---

## Playground Chat

### POST /api/workspaces/{name}/playground/chat

Interface de chat RAG (authentification OIDC requise).

```bash
curl -X POST https://rag.votre-domaine.fr/api/workspaces/mon-projet/playground/chat \
  -H "Cookie: _oidc_session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Comment fonctionne la réplication ?",
    "history": [],
    "llm": {"provider": "openai", "model": "gpt-4o"},
    "top_k": 5,
    "min_score": 0.3
  }'
```

---

## Codes d'erreur courants

| Code | Description | Action |
|---|---|---|
| `400` | Requête invalide (paramètres manquants ou incorrects) | Vérifier le body JSON |
| `401` | Token invalide ou session expirée | Vérifier la clé API ou se reconnecter |
| `403` | Accès refusé (permissions insuffisantes) | Vérifier les rôles Keycloak |
| `404` | Ressource non trouvée | Vérifier le nom du workspace/source |
| `409` | Conflit (ex : indexer déjà configuré, clé déjà révoquée) | Lire le message d'erreur |
| `422` | Entité non traitable (header réservé, format invalide) | Vérifier les contraintes |
| `503` | Service temporairement indisponible | Vérifier les logs du service |

---

*Fin du manuel utilisateur ag-flow.rag v1.0*
