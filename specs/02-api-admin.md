# RAG Service — API Administration

## Authentification

Tous les endpoints d'administration requièrent la **master key** :

```
Authorization: Bearer {RAG_MASTER_KEY}
```

La master key est définie dans le `.env` du service RAG au déploiement. C'est le seul secret d'amorçage — voir `06-secrets.md`.

---

## Workspaces

### Créer un workspace

```
POST /workspaces
```

```json
{
  "name": "harpocrate",
  "indexer": {
    "provider": "openai",
    "model": "text-embedding-3-small",
    "api_key_ref": "openai_embedding_key"
  },
  "rag": {
    "cnx": "postgresql://user:pass@host:5432/rag_harpocrate",
    "base": "rag_harpocrate"
  }
}
```

Réponse `201 Created` :

```json
{
  "id": "uuid...",
  "name": "harpocrate",
  "created_at": "2026-05-14T10:00:00Z"
}
```

Le service crée automatiquement la base pgvector dédiée avec la bonne dimension selon le modèle.

---

### Lister les workspaces

```
GET /workspaces
```

```json
[
  {
    "id": "uuid...",
    "name": "harpocrate",
    "provider": "openai",
    "model": "text-embedding-3-small",
    "sources_count": 1,
    "documents_count": 61,
    "last_indexed_at": "2026-05-14T09:00:00Z"
  }
]
```

---

### Détail d'un workspace

```
GET /workspaces/{name}
```

---

### Modifier un workspace

```
PATCH /workspaces/{name}
```

Si le changement concerne l'indexeur (provider ou modèle) et que des vecteurs existent déjà :

```json
// 409 Conflict
{
  "error": "indexer_change_requires_reindex",
  "current": "openai/text-embedding-3-small (dim=1536)",
  "requested": "voyage/voyage-3 (dim=1024)",
  "action": "POST /workspaces/harpocrate/reindex?confirm=true"
}
```

---

### Supprimer un workspace

```
DELETE /workspaces/{name}
```

Supprime la config, les jobs, les documents indexés et la base pgvector dédiée.

---

## Obtenir l'api_key d'un workspace

```
GET /workspaces/{name}/apikey
```

```json
{
  "workspace": "harpocrate",
  "api_key": "ws_xxx..."
}
```

Appelable à tout moment avec la master key. Utilisé par le script d'init Docker pour provisionner les agents. Voir `08-docker-init.md`.

---

## Sources git

### Ajouter une source

```
POST /workspaces/{name}/sources
```

```json
{
  "type": "git",
  "config": {
    "url": "https://github.com/gael/harpocrate",
    "branch": "main",
    "auth_ref": "github_token",
    "include": ["**/*.md"],
    "exclude": []
  }
}
```

---

### Supprimer une source

```
DELETE /workspaces/{name}/sources/{source_id}
```

---

## Réindexation

### Forcer une réindexation complète

```
POST /workspaces/{name}/reindex
```

Optionnel pour confirmer un changement d'indexeur :

```
POST /workspaces/{name}/reindex?confirm=true
```

Réponse `202 Accepted` — la réindexation tourne en tâche de fond.

```json
{
  "job_id": "uuid...",
  "status": "pending"
}
```

---

### Historique des jobs

```
GET /workspaces/{name}/jobs
```

```json
[
  {
    "id": "uuid...",
    "triggered_by": "webhook",
    "status": "done",
    "files_changed": 3,
    "files_skipped": 58,
    "duration_ms": 1240,
    "finished_at": "2026-05-14T09:01:02Z"
  }
]
```
