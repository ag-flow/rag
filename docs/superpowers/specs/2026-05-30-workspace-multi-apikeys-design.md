# Design — Multi-clés API par workspace

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Chaque workspace a actuellement une seule clé API (`api_key_fingerprint` + `api_key_ref` sur la table `workspaces`). Ce chantier remplace ce système par une table dédiée permettant de créer, nommer, révoquer et faire tourner autant de clés que souhaité.

**Règle de grace period** : lors d'une rotation, l'ancienne clé reste valide **72 heures** avant d'être automatiquement expirée.

---

## Base de données

### Migration — nouvelle table + suppression colonnes `workspaces`

```sql
-- Nouvelle table multi-clés
CREATE TABLE workspace_api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    fingerprint  TEXT NOT NULL,           -- SHA-256(api_key)
    api_key_ref  TEXT NOT NULL,           -- vault_ref Harpocrate
    revoked_at   TIMESTAMPTZ,            -- NULL = active
    rotated_at   TIMESTAMPTZ,            -- NULL = jamais rotée
                                         -- non-NULL = ancienne clé, expire à rotated_at + 72h
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (workspace_id, fingerprint)
);

CREATE INDEX workspace_api_keys_ws ON workspace_api_keys (workspace_id);
CREATE INDEX workspace_api_keys_fp ON workspace_api_keys (fingerprint);

-- Supprimer les colonnes devenues obsolètes sur workspaces
ALTER TABLE workspaces DROP COLUMN api_key_fingerprint;
ALTER TABLE workspaces DROP COLUMN api_key_ref;
```

### Validation d'une clé

Clé valide si :
- `revoked_at IS NULL`
- ET (`rotated_at IS NULL` OU `rotated_at > now() - interval '72 hours'`)

### Statut calculé

| Condition | Statut |
|---|---|
| `revoked_at IS NULL` ET `rotated_at IS NULL` | `active` |
| `revoked_at IS NULL` ET `rotated_at` récent (< 72h) | `grace_period` |
| `revoked_at IS NOT NULL` | `revoked` |
| `rotated_at` ancien (> 72h) ET `revoked_at IS NULL` | `expired` (traitée comme révoquée) |

---

## Backend

### Schemas (`schemas/workspace_apikeys.py`)

```
ApiKeyCreate    name: str
ApiKeyOut       id, name, fingerprint_preview (8 chars), status, created_at, revoked_at, rotated_at
ApiKeyCreated   id, name, fingerprint_preview, api_key (en clair, une seule fois), created_at
ApiKeyRotated   new_key_id, new_api_key (en clair), old_key_id, grace_until (rotated_at + 72h)
```

### Endpoints admin

```
GET    /workspaces/{name}/api-keys              → list[ApiKeyOut]
POST   /workspaces/{name}/api-keys              → ApiKeyCreated   (clé en clair unique)
POST   /workspaces/{name}/api-keys/{id}/rotate  → ApiKeyRotated   (nouvelle clé + ancienne en grace)
DELETE /workspaces/{name}/api-keys/{id}         → 204             (révocation immédiate)
```

Auth : `require_master_key_or_authenticated_admin`

### Service `services/workspace_apikeys.py`

- `list_keys(conn, workspace_name)` → list[ApiKeyOut]
- `create_key(conn, vault, vault_svc, workspace_name, name)` → ApiKeyCreated
  - Génère clé via `generate_api_key()`, SHA-256 fingerprint, stocke dans Harpocrate, INSERT
- `rotate_key(conn, vault, vault_svc, workspace_name, key_id)` → ApiKeyRotated
  - Génère nouvelle clé, INSERT nouvelle ligne
  - UPDATE ancienne : `rotated_at = now()`
  - Retourne les deux
- `revoke_key(conn, workspace_name, key_id)` → bool
  - UPDATE `revoked_at = now()`

### Authentification MCP — `mcp.py`

Remplacer le lookup `api_key_fingerprint` sur `workspaces` par :

```sql
SELECT w.id, w.name AS workspace_name, w.rag_cnx,
       ic.provider || '/' || ic.model AS indexer_used
FROM workspaces w
JOIN workspace_api_keys k ON k.workspace_id = w.id
JOIN indexer_configs ic ON ic.workspace_id = w.id
WHERE w.name = $1
  AND k.fingerprint = $2
  AND k.revoked_at IS NULL
  AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
```

L'`api_key_ref` pour la résolution Harpocrate vient maintenant de `workspace_api_keys.api_key_ref` (pas de `workspaces.api_key_ref`).

### Création workspace

`create_workspace` génère automatiquement une première clé nommée `"default"` après la création. La réponse 201 retourne toujours `api_key` en clair (comportement existant préservé).

---

## Frontend

### Nouvel onglet « API Keys » dans `WorkspaceDetailPanel`

Tableau :

| Nom | Fingerprint | Statut | Créée le | Actions |
|-----|-------------|--------|----------|---------|
| default | a3f2c1… | 🟢 Active | 30/05 | Rotate / Révoquer |
| CI/CD | b8e4d2… | 🟡 Grace 71h | 30/05 | Révoquer |
| old-prod | 7c1a9f… | 🔴 Révoquée | 28/05 | — |

**Créer une clé** → dialog :
- Champ Nom
- Clé affichée en clair une seule fois + bouton copie + avertissement "copiez maintenant"

**Rotate** → dialog de confirmation :
- Nouvelle clé affichée + bouton copie
- Message : "L'ancienne clé restera active 72 heures"

**Révoquer** → AlertDialog → révocation immédiate
- Les clés révoquées restent visibles (audit trail) en grisé

### i18n

Nouveau namespace `apikeys` (fr + en).

---

## Périmètre hors-scope

- Expiration automatique des clés après une durée (non demandé)
- Scope des clés (lecture seule vs lecture+écriture)
- Notifications webhook lors d'une révocation
