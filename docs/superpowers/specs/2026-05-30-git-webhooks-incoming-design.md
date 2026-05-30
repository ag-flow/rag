# Design — Webhooks git entrants (push → indexation réactive)

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Les sources git sont actuellement synchronisées par polling (`triggered_by='schedule'`). Ce chantier ajoute un mode réactif : GitHub/GitLab/Gitea/Bitbucket/Azure DevOps envoient un push event à un endpoint RAG, qui déclenche immédiatement l'indexation (`triggered_by='webhook'`).

Les deux modes sont **mutuellement exclusifs** : si `webhook_enabled = true` sur une source, le scheduler l'ignore.

---

## Périmètre

Providers couverts : `github`, `gitlab`, `gitea`, `bitbucket`, `azure-devops` (tous les `GitHost` existants).

---

## Section 1 — Données

### Migration `workspace_sources`

```sql
ALTER TABLE workspace_sources
  ADD COLUMN webhook_enabled BOOLEAN NOT NULL DEFAULT false;
```

`webhook_enabled = true` → source pilotée par push, exclue du scheduler.

### Champs JSONB `config` (ajout)

| Clé | Type | Rôle |
|---|---|---|
| `webhook_secret_ref` | `str` | Vault ref Harpocrate — `${vault://vault_name:/sources/{workspace}/{source}/webhook_secret}` |
| `webhook_branch_filter` | `str \| null` | Branche à surveiller ; si `null`, utilise la branche déjà configurée sur la source |

Le path Harpocrate suit la convention : `sources/{workspace_name}/{source_name}/webhook_secret`.

---

## Section 2 — Endpoint de réception

### URL

```
POST /api/webhooks/git/{workspace_name}/{source_name}
```

Endpoint public — pas d'`Authorization` header. L'authentification est la signature du payload.

### Flow

```
1. Charger la source (workspace_name + source_name)
   → 404 si introuvable ou webhook_enabled = false

2. Résoudre webhook_secret depuis Harpocrate (webhook_secret_ref)
   → 500 si irrésolvable

3. Valider la signature selon git_provider
   → 401 si invalide

4. Extraire la branche du payload
   → Comparer avec la branche configurée
   → 200 OK silencieux si branche non correspondante

5. Créer index_job (triggered_by='webhook', status='pending')
   → 202 Accepted { job_id, status: "pending" }
```

### Validateurs — `rag/sync/webhook_validators.py`

Interface : `validate(provider, secret, headers, raw_body) -> bool`

| Provider | Header | Mécanisme |
|---|---|---|
| `github` | `X-Hub-Signature-256` | HMAC-SHA256 : `sha256=<hex>` |
| `gitea` | `X-Gitea-Signature` | HMAC-SHA256 : `<hex>` |
| `gitlab` | `X-Gitlab-Token` | Comparaison constante (`hmac.compare_digest`) |
| `bitbucket` | `X-Hub-Signature` | HMAC-SHA256 : `sha256=<hex>` |
| `azure-devops` | `Authorization` Basic | Secret = mot de passe Basic Auth |

Chaque validateur est une fonction pure, testable en isolation.

### Parseurs de branche — `rag/sync/webhook_parsers.py`

Interface : `extract_branch(provider, payload) -> str | None`

| Provider | Champ payload |
|---|---|
| `github`, `gitea`, `gitlab` | `payload["ref"]` → strip `refs/heads/` |
| `bitbucket` | `payload["push"]["changes"][0]["new"]["name"]` |
| `azure-devops` | `payload["resource"]["refUpdates"][0]["name"]` → strip `refs/heads/` |

Retourne `None` si le champ est absent (payload non-push ignoré silencieusement).

---

## Section 3 — Intégration scheduler

### Filtre dans `schedule_due_sources`

```sql
WHERE s.next_sync_at IS NOT NULL
  AND s.next_sync_at <= now()
  AND s.webhook_enabled = false     -- ← ajout
  AND NOT EXISTS (
      SELECT 1 FROM index_jobs j
      WHERE j.source_id = s.id
        AND j.status IN ('pending', 'running')
  )
```

### Activation webhook (PATCH source via API admin)

1. Générer un secret : `secrets.token_hex(32)`
2. Pousser dans Harpocrate au path structuré
3. Stocker `webhook_secret_ref` dans JSONB config
4. `webhook_enabled = true`, `next_sync_at = NULL`
5. Retourner le secret en clair **une seule fois** dans la réponse

### Désactivation webhook

1. Supprimer le secret dans Harpocrate
2. Vider `webhook_secret_ref` du JSONB
3. `webhook_enabled = false`, `next_sync_at = now()`
4. La source réintègre immédiatement le pool scheduler

### Rotation du secret

```
POST /api/admin/workspaces/{name}/sources/{source_name}/webhook/rotate-secret
```

1. Générer un nouveau `secrets.token_hex(32)`
2. Écraser dans Harpocrate au même path (la `webhook_secret_ref` ne change pas)
3. Retourner le nouveau secret en clair une seule fois

---

## Section 4 — UI

### Badge mode sur chaque source

- `Schedule` (gris) si `webhook_enabled = false`
- `Webhook` (vert) si `webhook_enabled = true`

### Dialog "Activer le webhook"

Affiché après clic sur **"Activer le webhook"** dans le menu source :

- URL de livraison à copier : `{RAG_PUBLIC_URL}/api/webhooks/git/{workspace}/{source}`
- Secret généré affiché **une seule fois** avec bouton copie + avertissement
- Rappel : content type `application/json`, événement `Push events` uniquement

### Source avec webhook actif

- Bouton **Rotation du secret** → nouveau dialog avec le même pattern one-shot
- Bouton **Désactiver** → confirmation → repasse en mode Schedule

### i18n

Nouveau namespace `git_webhooks` (fr + en), séparé du namespace `sources` existant.

---

## Périmètre hors-scope

- Retry automatique si le job échoue (la rotation manuelle du secret est le seul mécanisme de récupération côté webhook)
- Log d'audit des appels entrants (pas de table `incoming_webhook_calls`)
- Support de plusieurs webhooks par source (un provider = un webhook)
- Filtrage par tag ou path (seule la branche est filtrée)
