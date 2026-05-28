# RAG Service — Webhooks

## Principe

Chaque workspace peut configurer **plusieurs webhooks** appelés à la fin de chaque indexation — qu'elle soit déclenchée par un changement git ou par un push manuel.

Tous les webhooks configurés sur le workspace sont appelés en parallèle.

L'appel est **fire and forget** — une seule tentative par webhook, pas de retry. Un audit log des appels est conservé 24h et consultable via API.

---

## Correlation ID

Chaque indexation est associée à un `X-Correlation-ID` retransmis dans tous les webhooks déclenchés par cet événement :

| Déclencheur | Valeur du `X-Correlation-ID` |
|---|---|
| Push manuel (`POST /index`) | UUID généré par le service, retourné dans le `202 Accepted` |
| Sync git | Hash du commit git ayant déclenché la sync |

Le client ne peut pas fixer cet ID — le service en est seul maître.

---

## Headers réservés

Les headers suivants sont gérés exclusivement par le service RAG. Le configurateur ne peut pas les déclarer dans `headers[]` :

| Header | Rôle | Présent si |
|---|---|---|
| `X-Correlation-ID` | Corrélation événement — géré par le service | Toujours |
| `X-RAG-Signature` | Signature HMAC du payload — géré par le service | Toujours |
| `X-Git-Repo` | URL du dépôt git source — géré par le service | Déclenchement git uniquement |
| `X-Git-Branch` | Branche git — géré par le service | Déclenchement git uniquement |
| `X-Git-Commit` | Hash du commit — géré par le service | Déclenchement git uniquement |

**API** — si un header réservé est présent dans `headers[]` à la création ou modification :

```json
// 422 Unprocessable Entity
{
  "error": "reserved_header",
  "message": "Header 'X-Correlation-ID' is reserved and cannot be configured.",
  "reserved_headers": ["X-Correlation-ID", "X-RAG-Signature"]
}
```

**IHM** — validation inline au blur ou à la soumission, même message. Le bouton de confirmation reste désactivé tant que le conflit existe.

---

## Modèle de données

### Table `workspace_webhooks`

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
```

### Table `webhook_headers`

```sql
CREATE TABLE webhook_headers (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  webhook_id  UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,         -- nom du header, ex: "X-Api-Key"
  value       TEXT,                  -- valeur en clair si vault absent
  vault_ref   TEXT,                  -- référence vault si stockage sécurisé
                                     -- ex: ${vault://harpocrate-1:/workspaces/harpocrate/hooks/abc123/headers/X-Api-Key}
  enabled     BOOLEAN DEFAULT true
);
```

Si `vault` est renseigné à la création :
- Le service pousse la `value` dans Harpocrate au path structuré
- Stocke la référence `vault_ref` en base
- La valeur en clair n'est jamais persistée

Si `vault` est absent :
- La `value` est stockée en clair en base

---

## API de gestion des webhooks

### Lister les webhooks d'un workspace

```
GET /workspaces/{name}/webhooks
Authorization: Bearer {master_key}
```

```json
[
  {
    "id": "uuid...",
    "name": "agflow-notify",
    "url": "https://agflow.yoops.org/hooks/rag-indexed",
    "enabled": true,
    "headers": [
      {
        "id": "uuid...",
        "name": "X-Api-Key",
        "value": null,
        "vault_ref": "${vault://harpocrate-1:/workspaces/harpocrate/hooks/abc123/headers/X-Api-Key}",
        "enabled": true
      }
    ]
  }
]
```

La `value` n'est jamais retournée dans les réponses API — uniquement la `vault_ref` si applicable.

### Ajouter un webhook

```
POST /workspaces/{name}/webhooks
Authorization: Bearer {master_key}
```

```json
[
  {
    "name": "agflow-notify",
    "url": "https://agflow.yoops.org/hooks/rag-indexed",
    "enabled": true,
    "headers": [
      {
        "name": "X-Api-Key",
        "value": "pgp_api_xxxx",
        "vault": "harpocrate-1",
        "enabled": true
      }
    ]
  }
]
```

Le champ `vault` indique dans quel coffre Harpocrate stocker la valeur. Le service construit le path :

```
${vault://harpocrate-1:/workspaces/{workspace}/hooks/{hook_id}/headers/{header_name}}
```

Si un header réservé est présent → `422 Unprocessable Entity` (voir section Headers réservés).

### Modifier un webhook

```
PATCH /workspaces/{name}/webhooks/{webhook_id}
Authorization: Bearer {master_key}
```

```json
{
  "enabled": false
}
```

### Modifier un header

```
PATCH /workspaces/{name}/webhooks/{webhook_id}/headers/{header_id}
Authorization: Bearer {master_key}
```

```json
{
  "value": "pgp_api_new_xxx",
  "vault": "harpocrate-1"
}
```

Le service met à jour la valeur dans Harpocrate au même path — la `vault_ref` ne change pas.

### Supprimer un webhook

```
DELETE /workspaces/{name}/webhooks/{webhook_id}
Authorization: Bearer {master_key}
```

Supprime le webhook, ses headers, et les secrets associés dans Harpocrate.

---

## Payload envoyé

### Déclenchement git

```http
POST {webhook_url}
Content-Type: application/json
X-Correlation-ID: abc123def456                              ← hash du commit (réservé)
X-RAG-Signature: sha256=xxx                                 ← réservé, géré par le service
X-Git-Repo: https://github.com/gael/harpocrate             ← réservé, git uniquement
X-Git-Branch: main                                          ← réservé, git uniquement
X-Git-Commit: abc123def456                                  ← réservé, git uniquement
X-Api-Key: pgp_api_xxxx                                     ← header custom configuré

{
  "event": "indexation.completed",
  "workspace": "harpocrate",
  "triggered_by": "git",
  "job_id": "uuid...",
  "status": "done",
  "files_changed": 3,
  "files_skipped": 58,
  "duration_ms": 1240,
  "finished_at": "2026-05-14T09:01:02Z",
  "error_message": null
}
```

### Déclenchement push

```http
POST {webhook_url}
Content-Type: application/json
X-Correlation-ID: 7f3a1b2c-9e4d-4f8a-b1c2-3d4e5f6a7b8c   ← UUID (réservé)
X-RAG-Signature: sha256=xxx                                 ← réservé, géré par le service
X-Api-Key: pgp_api_xxxx                                     ← header custom configuré

{
  "event": "indexation.completed",
  "workspace": "harpocrate",
  "triggered_by": "push",
  "job_id": "uuid...",
  "status": "done",
  "files_changed": 1,
  "files_skipped": 0,
  "duration_ms": 340,
  "finished_at": "2026-05-14T09:05:00Z",
  "error_message": null
}
```

---

## IHM — Header par défaut

À la création d'un webhook via l'interface, un header est pré-rempli mais désactivé :

```json
{
  "name": "X-Api-Key",
  "value": "",
  "vault": "harpocrate-1",
  "enabled": false
}
```

L'utilisateur renseigne la valeur et active le header. Le coffre cible est pré-rempli avec l'instance Harpocrate par défaut du service.

---

## Audit log — table `webhook_calls`

```sql
CREATE TABLE webhook_calls (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  webhook_id      UUID NOT NULL REFERENCES workspace_webhooks(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES index_jobs(id),
  correlation_id  TEXT NOT NULL,
  triggered_by    TEXT NOT NULL,
  webhook_url     TEXT NOT NULL,
  http_status     INT,
  error           TEXT,
  duration_ms     INT,
  called_at       TIMESTAMPTZ DEFAULT now()
);
```

Les entrées sont automatiquement purgées après **24 heures**.

---

## API de consultation de l'audit log

### Lister les appels d'un workspace

```
GET /workspaces/{name}/webhooks/calls
Authorization: Bearer {master_key}
```

Paramètres optionnels :

| Paramètre | Type | Description |
|---|---|---|
| `webhook_id` | uuid | Filtrer sur un webhook spécifique |
| `correlation_id` | string | Filtrer sur un événement spécifique |
| `status` | `success` \| `error` | Filtrer par statut |
| `limit` | int | Nombre de résultats (défaut: 50) |

### Purger manuellement l'audit log

```
DELETE /workspaces/{name}/webhooks/calls
Authorization: Bearer {master_key}
```

---

## Comportement selon le type de déclenchement

| Déclencheur | Moment d'appel | X-Correlation-ID |
|---|---|---|
| Sync git | Fin du job (`done` ou `error`) | Hash du commit git |
| Push asynchrone | Fin du traitement en arrière-plan | UUID retourné dans le `202 Accepted` |

Tous les webhooks activés (`enabled: true`) du workspace sont appelés en parallèle.
