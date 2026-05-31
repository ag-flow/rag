# 08 — Webhooks sortants

Les webhooks sortants permettent de notifier vos systèmes externes (ag.flow, Slack, CI/CD, etc.) à la fin de chaque indexation.

---

## Principe

Après chaque indexation réussie (ou en erreur), le service RAG envoie une requête HTTP POST à tous les webhooks configurés pour le workspace concerné.

- **Envoi en parallèle** de tous les webhooks du workspace
- **Fire and forget** : une seule tentative, pas de retry
- **Audit log** conservé 24 heures

---

## Configurer un webhook

### Via l'interface

1. Onglet **Webhooks** du workspace
2. Cliquez **+ Ajouter un webhook**
3. Remplissez le formulaire :

| Champ | Obligatoire | Description |
|---|---|---|
| **Nom** | Oui | Identifiant unique dans le workspace (ex : `agflow-notify`) |
| **URL** | Oui | URL qui recevra les notifications POST |
| **Activé** | — | Active/désactive sans supprimer |

**Headers personnalisés (optionnel) :**

Ajoutez des headers HTTP qui seront envoyés avec chaque notification. Utile pour l'authentification :

| Champ | Description |
|---|---|
| **Nom** | Nom du header (ex : `X-Api-Key`, `Authorization`) |
| **Valeur** | Valeur du header |
| **Coffre** | Si renseigné, la valeur est stockée dans Harpocrate (recommandé pour les secrets) |
| **Activé** | Active/désactive ce header sans le supprimer |

> **Sécurité :** Si vous configurez un header avec un token secret (ex : `X-Api-Key: mon_secret`), activez l'option **Coffre** pour que la valeur soit chiffrée dans Harpocrate et jamais stockée en clair.

**Headers réservés (gérés automatiquement par le service) :**

Ces headers sont ajoutés par le service RAG — vous ne pouvez pas les configurer manuellement :

| Header | Description | Présent si |
|---|---|---|
| `X-Correlation-ID` | UUID ou hash commit pour corrélation | Toujours |
| `X-RAG-Signature` | Signature HMAC-SHA256 du payload | Toujours (si `RAG_WEBHOOK_SECRET` configuré) |
| `X-Git-Repo` | URL du dépôt git source | Déclenchement git uniquement |
| `X-Git-Branch` | Branche git | Déclenchement git uniquement |
| `X-Git-Commit` | Hash du commit | Déclenchement git uniquement |

### Via l'API

```bash
# Webhook simple
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "agflow-notify",
    "url": "https://agflow.votre-domaine.fr/hooks/rag-indexed",
    "enabled": true
  }'
```

```bash
# Webhook avec header d'authentification chiffré dans Harpocrate
curl -X POST https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "slack-notify",
    "url": "https://hooks.slack.com/services/xxx/yyy/zzz",
    "enabled": true,
    "headers": [
      {
        "name": "Content-Type",
        "value": "application/json",
        "enabled": true
      },
      {
        "name": "X-Slack-Signature",
        "value": "mon_secret_slack",
        "vault": "coffre-principal",
        "enabled": true
      }
    ]
  }'
```

---

## Format des payloads

### Déclenchement git (commit détecté)

```http
POST https://votre-serveur.fr/hooks/rag-indexed
Content-Type: application/json
X-Correlation-ID: abc123def456789
X-RAG-Signature: sha256=a3f2c1...
X-Git-Repo: https://github.com/mon-org/mon-repo
X-Git-Branch: main
X-Git-Commit: abc123def456789
X-Api-Key: votre_token_configuré

{
  "event": "indexation.completed",
  "workspace": "mon-projet",
  "triggered_by": "git",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "done",
  "files_changed": 3,
  "files_skipped": 58,
  "duration_ms": 1240,
  "finished_at": "2026-05-31T09:01:02Z",
  "error_message": null
}
```

### Déclenchement push manuel (via `/index`)

```http
POST https://votre-serveur.fr/hooks/rag-indexed
Content-Type: application/json
X-Correlation-ID: 7f3a1b2c-9e4d-4f8a-b1c2-3d4e5f6a7b8c
X-RAG-Signature: sha256=b4e3d2...

{
  "event": "indexation.completed",
  "workspace": "mon-projet",
  "triggered_by": "push",
  "job_id": "uuid...",
  "status": "done",
  "files_changed": 1,
  "files_skipped": 0,
  "duration_ms": 340,
  "finished_at": "2026-05-31T09:05:00Z",
  "error_message": null
}
```

### Champs du payload

| Champ | Type | Description |
|---|---|---|
| `event` | string | Toujours `indexation.completed` |
| `workspace` | string | Nom du workspace |
| `triggered_by` | string | `git` / `push` / `schedule` / `webhook` / `manual` |
| `job_id` | UUID | Identifiant unique du job |
| `status` | string | `done` / `error` / `skipped` |
| `files_changed` | int | Fichiers nouvellement indexés |
| `files_skipped` | int | Fichiers ignorés (contenu inchangé) |
| `duration_ms` | int | Durée de l'indexation en millisecondes |
| `finished_at` | datetime | Horodatage de fin (ISO 8601) |
| `error_message` | string | Message d'erreur si `status=error`, sinon `null` |

---

## Vérifier la signature HMAC

Si `RAG_WEBHOOK_SECRET` est configuré dans votre `.env`, chaque requête inclut le header `X-RAG-Signature`.

Pour vérifier la signature côté récepteur :

```python
import hashlib
import hmac

def verify_rag_signature(body: bytes, signature: str, secret: str) -> bool:
    """Vérifie la signature HMAC-SHA256 d'un payload webhook RAG."""
    expected = "sha256=" + hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

# Exemple d'usage dans FastAPI
from fastapi import Request, HTTPException

@app.post("/hooks/rag-indexed")
async def handle_rag_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-RAG-Signature", "")
    
    if not verify_rag_signature(body, signature, "votre_RAG_WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = await request.json()
    # Traiter le payload...
```

```javascript
// Exemple en Node.js
const crypto = require('crypto');

function verifyRagSignature(body, signature, secret) {
  const expected = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(body)
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  );
}
```

---

## Corrélation avec le push manuel

Si vous appelez `/workspaces/{name}/index` (indexation push), la réponse contient un `X-Correlation-ID`. Ce même ID sera dans le header `X-Correlation-ID` du webhook envoyé à la fin du traitement.

```bash
# Pousser un document et récupérer le correlation ID
response=$(curl -si -X POST https://rag.votre-domaine.fr/workspaces/mon-projet/index \
  -H "Authorization: Bearer $WORKSPACE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"path": "docs/guide.md", "content": "# Guide\n..."}')

correlation_id=$(echo "$response" | grep -i "X-Correlation-ID" | awk '{print $2}' | tr -d '\r')

echo "Job soumis, correlation ID: $correlation_id"
# Votre webhook recevra ce même correlation_id dans ses headers
```

---

## Audit log des appels

Chaque appel webhook est conservé 24 heures dans un log d'audit.

### Consulter le log

**Via l'interface :** Onglet **Webhooks** > cliquez sur un webhook > onglet **Historique des appels**

**Via l'API :**
```bash
# Tous les appels du workspace
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/calls"

# Filtrer par statut
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/calls?status=error"

# Filtrer par correlation ID
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/calls?correlation_id=abc123"

# Filtrer sur un webhook spécifique
curl -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/calls?webhook_id={webhook_id}"
```

Réponse :
```json
[
  {
    "id": "uuid...",
    "webhook_id": "uuid...",
    "job_id": "uuid...",
    "correlation_id": "abc123def456",
    "triggered_by": "git",
    "webhook_url": "https://agflow.votre-domaine.fr/hooks/rag-indexed",
    "http_status": 200,
    "error": null,
    "duration_ms": 145,
    "called_at": "2026-05-31T09:01:02Z"
  }
]
```

### Purger le log manuellement

```bash
curl -X DELETE -H "Authorization: Bearer $RAG_MASTER_KEY" \
  "https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/calls"
```

---

## Modifier un webhook

```bash
# Désactiver un webhook
curl -X PATCH https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/{webhook_id} \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Changer l'URL
curl -X PATCH https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/{webhook_id} \
  -H "Authorization: Bearer $RAG_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://nouvelle-url.fr/hook"}'
```

---

## Supprimer un webhook

La suppression retire également les secrets associés dans Harpocrate.

**Via l'interface :** Menu `⋮` > **Supprimer le webhook**

**Via l'API :**
```bash
curl -X DELETE https://rag.votre-domaine.fr/api/admin/workspaces/mon-projet/webhooks/{webhook_id} \
  -H "Authorization: Bearer $RAG_MASTER_KEY"
```

---

## Prochaine étape

→ [09 — Enrichissement LLM](09-enrichissement.md)
