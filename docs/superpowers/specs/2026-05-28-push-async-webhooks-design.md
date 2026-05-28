# Design — Push asynchrone + Webhooks

**Date** : 2026-05-28  
**Specs source** : `specs/03-api-workspace-2.md`, `specs/11-webhooks.md`  
**Périmètre** : backend (FastAPI + asyncpg) + frontend (React + TanStack Query)

---

## 1. Contexte

Le endpoint `POST /workspaces/{name}/index` est aujourd'hui synchrone : il renvoie
`indexed` ou `skipped` directement dans la réponse. Ce jalon le rend **asynchrone** :
202 immédiat, traitement en arrière-plan, résultat notifié par webhook.

Les webhooks sont un nouveau sous-système complet : CRUD de configuration,
dispatch fire-and-forget signé HMAC, audit log 24h, intégration Harpocrate
pour les headers secrets.

C'est un **breaking change** assumé sur le contrat du endpoint `/index`.

---

## 2. Modèle de données

### Migration 018 — extensions `index_jobs` + `push_job_payloads`

```sql
-- Ajoute 'skipped' au status (push dédupliqué en arrière-plan)
ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_status_check;
ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_status_check
    CHECK (status IN ('pending', 'running', 'done', 'error', 'skipped'));

-- Correlation ID : UUID v4 pour push (set à la création),
-- hash commit git pour les jobs git (set après head_commit dans l'executor)
ALTER TABLE index_jobs ADD COLUMN correlation_id TEXT;

-- Payload temporaire pour les push jobs — supprimé après traitement
CREATE TABLE push_job_payloads (
    job_id   UUID PRIMARY KEY REFERENCES index_jobs(id) ON DELETE CASCADE,
    path     TEXT NOT NULL,
    content  TEXT NOT NULL
);
```

### Migration 019 — webhooks

```sql
CREATE TABLE workspace_webhooks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    url           TEXT NOT NULL,
    enabled       BOOLEAN DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(workspace_id, name)
);

CREATE TABLE webhook_headers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id  UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    value       TEXT,       -- valeur en clair si vault absent
    vault_ref   TEXT,       -- référence Harpocrate si stockage sécurisé
    enabled     BOOLEAN DEFAULT true
);
```

### Migration 020 — audit log

```sql
CREATE TABLE webhook_calls (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    webhook_id     UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
    job_id         UUID NOT NULL REFERENCES index_jobs(id),
    correlation_id TEXT NOT NULL,
    triggered_by   TEXT NOT NULL,
    webhook_url    TEXT NOT NULL,
    http_status    INT,
    error          TEXT,
    duration_ms    INT,
    called_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_webhook_calls_workspace ON webhook_calls(workspace_id, called_at DESC);
CREATE INDEX idx_webhook_calls_purge     ON webhook_calls(called_at);
```

---

## 3. Push asynchrone — backend

### 3.1 Endpoint `POST /workspaces/{name}/index`

Nouveau comportement :

1. Normalize + validate `path`
2. Génère `correlation_id` = UUID v4
3. `INSERT index_jobs (triggered_by='push', status='pending', correlation_id)`
4. `INSERT push_job_payloads (job_id, path, content)`
5. Retourne `202 Accepted` + header `X-Correlation-ID` + `{job_id, status: "pending"}`

Les schémas Pydantic `PushIndexedResponse`, `PushSkippedResponse`, `PushResponse`
sont remplacés par `PushAsyncResponse(job_id: str, status: Literal["pending"])`.

Le service `push_document` existant est supprimé — la logique de déduplication
migre dans `_execute_push_job` côté worker.

### 3.2 Worker — branchement push / git

`pick_next_pending_job` retourne désormais `triggered_by` et `correlation_id`
dans son `RETURNING`. `JobToProcess` reçoit ces deux champs.

Dans `execute_next_pending_job` :

```
triggered_by == 'push'  →  _execute_push_job(job, ...)
sinon                   →  _execute_git_job(job, ...)   ← renommage de _process_job
```

### 3.3 `_execute_push_job`

```
try:
  1. SELECT path, content FROM push_job_payloads WHERE job_id
  2. content_hash = "sha256:" + sha256(content)
  3. SELECT content_hash FROM indexed_documents WHERE workspace_id + path
  4. Si hash identique :
       UPDATE index_jobs SET status='skipped', finished_at=now(), duration_ms=...
  5. Sinon :
       indexer.index_file(workspace_id, path, content, content_hash, indexer_used)
       UPDATE index_jobs SET status='done', finished_at=now(), duration_ms=..., files_changed=1
  6. dispatch_webhooks(job, final_status, config_pool, resolver, settings)
finally:
  DELETE FROM push_job_payloads WHERE job_id  ← toujours nettoyé, même en cas d'erreur
```

En cas d'exception : `_mark_job_error` existant, puis `dispatch_webhooks` avec `status='error'`.

### 3.4 `_execute_git_job` (ex-`_process_job`)

Deux ajouts par rapport au code actuel :

- Après `head_commit(dest)` : `UPDATE index_jobs SET correlation_id = current_commit WHERE id = job_id`
- Après `head_commit` : `correlation_id` set sur le job. Si le job échoue avant `head_commit` (clone raté, etc.), fallback : `correlation_id = str(job.job_id)`
- En fin de pipeline (step 6, après mark done) : `dispatch_webhooks(job, 'done', ...)`
- En cas d'erreur dans `execute_next_pending_job` : `dispatch_webhooks(job, 'error', ...)`

---

## 4. Sous-système webhooks

### 4.1 Service `dispatch_webhooks`

Client HTTP : `httpx` (async natif). À ajouter aux dépendances backend (`uv add httpx`).

Signature : `async def dispatch_webhooks(job, status, config_pool, resolver, settings) -> None`

Appelé après chaque job (push ou git). Fire-and-forget — ne lève jamais d'exception.

```
1. SELECT workspace_webhooks WHERE workspace_id AND enabled=true
2. Si aucun webhook → return immédiatement
3. asyncio.gather(*[_call_webhook(wh, ...) for wh in webhooks])
```

`_call_webhook` pour chaque webhook :

```
a. Résout les headers enabled : vault_ref → resolver, sinon value en clair
b. Construit le payload JSON :
   {event, workspace, triggered_by, job_id, status,
    files_changed, files_skipped, duration_ms, finished_at, error_message}
c. Signe : X-RAG-Signature = "sha256=" + hmac_sha256(RAG_WEBHOOK_SECRET, payload_bytes).hex()
d. Headers réservés : X-Correlation-ID (toujours)
                      X-Git-Repo, X-Git-Branch, X-Git-Commit (git uniquement)
e. POST HTTP (httpx async), timeout=10s
f. INSERT webhook_calls (http_status ou error, duration_ms)
```

Toutes les exceptions dans `_call_webhook` sont attrapées et loggées — un
webhook qui échoue n'affecte pas les autres.

### 4.2 Clé HMAC

`RAG_WEBHOOK_SECRET: str | None` dans `config.py` (Pydantic Settings).  
Si absent : `X-RAG-Signature` est omis, warning structlog à chaque dispatch.

### 4.3 Headers réservés

Constante dans le service :

```python
RESERVED_HEADERS = frozenset({
    "x-correlation-id", "x-rag-signature",
    "x-git-repo", "x-git-branch", "x-git-commit",
})
```

Validation à la création et modification d'un header (comparaison lowercase).
Erreur `422` avec `{"error": "reserved_header", "message": "...", "reserved_headers": [...]}`.

### 4.4 API de gestion (auth master_key)

| Méthode | URL | Action |
|---|---|---|
| `GET` | `/workspaces/{name}/webhooks` | Lister (headers sans `value`) |
| `POST` | `/workspaces/{name}/webhooks` | Créer avec headers |
| `PATCH` | `/workspaces/{name}/webhooks/{id}` | Modifier (enabled, url, name) |
| `DELETE` | `/workspaces/{name}/webhooks/{id}` | Supprimer (cascade + purge Harpocrate) |
| `PATCH` | `/workspaces/{name}/webhooks/{id}/headers/{hid}` | Modifier header |
| `GET` | `/workspaces/{name}/webhooks/calls` | Audit log |
| `DELETE` | `/workspaces/{name}/webhooks/calls` | Purge manuelle |

Paramètres `GET /calls` : `webhook_id`, `correlation_id`, `status` (`success`|`error`), `limit` (défaut 50).

La `value` d'un header n'est **jamais** retournée dans les réponses API.

### 4.5 Intégration Harpocrate

À la création d'un header avec `vault` renseigné :

```
path = /workspaces/{workspace}/hooks/{webhook_id}/headers/{header_name}
→ push value dans Harpocrate au path structuré
→ stocker vault_ref en base
→ ne pas persister value en clair
```

À la suppression d'un webhook : purge des secrets Harpocrate associés pour chaque
header avec `vault_ref`.

À la modification d'un header : update au même path Harpocrate (`vault_ref` inchangée).

### 4.6 Purge automatique de l'audit log

Dans le cycle du `SyncWorker` (1 appel best-effort par tick) :

```sql
DELETE FROM webhook_calls WHERE called_at < now() - interval '24 hours'
```

Une exception ne tue pas le cycle.

---

## 5. Frontend

### 5.1 Structure

Nouvel onglet **"Webhooks"** dans la page détail workspace, aux côtés de Jobs et Sources.
Deux sous-vues : liste des webhooks + audit log.

### 5.2 Liste des webhooks

- Carte par webhook : nom, URL, compteur de headers, toggle enabled (PATCH inline)
- Bouton suppression avec dialog de confirmation
- Bouton "+ Ajouter" ouvre le formulaire

### 5.3 Formulaire création / édition

Champs : `name`, `url`, liste de headers.

Pour chaque header :
- `name` : saisie libre, validation réservé au blur (inline error, pas de toast)
- `value` : champ password (jamais ré-affiché après save)
- `vault` : sélecteur parmi vaults Harpocrate (`GET /admin/harpocrate-vaults`)
- `enabled` : toggle

Le bouton de confirmation reste désactivé tant qu'un header réservé est déclaré.

Header `X-Api-Key` pré-rempli mais désactivé à la création (convention spec).

### 5.4 Audit log

Filtres : webhook (select), statut (success/error), correlation_id (text).  
Tableau : date, webhook, http_status (coloré 2xx vert / 4xx-5xx rouge), durée, correlation_id.  
Polling TanStack Query toutes les 30s.  
Bouton "Purger l'audit" avec confirmation.

### 5.5 i18n

Toutes les chaînes dans `fr.json` / `en.json` sous le namespace `webhooks`.

---

## 6. Tests

### Backend

- `test_push_async_202` : POST /index → 202 + X-Correlation-ID + job en DB
- `test_push_worker_indexed` : worker traite push job → status='done', payload supprimé
- `test_push_worker_skipped` : contenu identique → status='skipped'
- `test_push_worker_error` : indexer lève exception → status='error'
- `test_webhook_dispatch_called` : après job done, webhooks appelés en parallèle
- `test_webhook_reserved_header_rejected` : 422 sur X-Correlation-ID dans headers
- `test_webhook_hmac_signature` : signature correcte sur le payload
- `test_webhook_call_audit_logged` : INSERT webhook_calls après dispatch
- `test_webhook_purge` : DELETE webhook_calls > 24h dans le cycle worker
- CRUD webhooks : create / list / patch / delete (avec et sans vault)

### Frontend

- `WebhookList` : rendu liste, toggle, suppression
- `WebhookForm` : validation header réservé, bouton désactivé, champ value masqué
- `WebhookCallsLog` : filtres, polling, purge
