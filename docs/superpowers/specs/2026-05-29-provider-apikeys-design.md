# Design — Gestion des clés API provider dans Harpocrate

**Date :** 2026-05-29
**Périmètre :** backend (FastAPI + asyncpg) + frontend (React + TanStack Query)
**Jalon suivant :** référencement de ces clés dans le formulaire de création de workspace

---

## 1. Contexte et motivation

Actuellement, créer un workspace nécessite de saisir la clé API du provider d'embedding
directement dans le formulaire. C'est peu pratique quand la même clé est réutilisée sur
plusieurs workspaces.

Ce jalon introduit un catalogue de clés API provider pré-stockées dans Harpocrate,
accessibles depuis un nouvel onglet "Apikeys" dans la page de détail d'un coffre
Harpocrate. Le prochain jalon connectera ce catalogue au formulaire de création de workspace.

---

## 2. Modèle de données

### Migration 024

```sql
CREATE TABLE provider_api_keys (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id      TEXT NOT NULL,
    label       TEXT NOT NULL,
    provider    TEXT NOT NULL,
    vault_id    UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, provider, key_id)
);
```

**Champs :**
- `key_id` — slug fonctionnel unique par `(vault_id, provider)` ; regex `^[a-zA-Z0-9_-]+$`, 1–64 chars
- `label` — nom affiché dans les listes de sélection
- `provider` — chaîne provider (ex: `openai`, `voyage`, `mistral`, `jina`, `cohere`, `ollama`)
- `vault_id` — coffre Harpocrate qui héberge le secret ; `ON DELETE RESTRICT` interdit
  de supprimer un coffre portant des clés
- `harpo_path` — chemin complet dans Harpocrate : `/<vault-name>/<provider>/<key_id>`

La valeur (la clé API elle-même) est stockée **uniquement dans Harpocrate** au path
`harpo_path`. Elle n'est jamais persistée en DB.

### Protection suppression

`DELETE /provider-keys/{id}` vérifie qu'aucune entrée de `workspaces` ne référence
le `harpo_path` (recherche par LIKE `%harpo_path%` sur les colonnes `api_key_ref`
et équivalentes). Retourne `409 Conflict` si une référence existe.
Pour ce jalon, le check sera toujours 0 (aucun workspace ne référence encore ces clés).

---

## 3. Backend API

Router monté sous `/api/admin/harpocrate-vaults/{vault_id}/provider-keys`.
Auth : `require_master_key_or_authenticated_admin` (identique au reste du router vaults).

### Endpoints

| Méthode | URL | Status | Action |
|---|---|---|---|
| `GET` | `.../provider-keys` | 200 | Lister toutes les clés du coffre (sans valeur) |
| `POST` | `.../provider-keys` | 201 | Créer une clé |
| `PATCH` | `.../provider-keys/{id}` | 200 | Mettre à jour label ou remplacer valeur |
| `DELETE` | `.../provider-keys/{id}` | 204 | Supprimer si non référencée |

### Payload création (POST)

```json
{
  "key_id": "prod-openai",
  "label": "OpenAI production",
  "provider": "openai",
  "value": "sk-..."
}
```

### Payload PATCH

```json
{ "label": "Nouveau label" }
```
ou
```json
{ "value": "sk-nouvelle-valeur..." }
```

Les deux champs sont indépendants et optionnels. Si `value` est fourni, le secret
est mis à jour dans Harpocrate au même `harpo_path`.

### Réponse (toujours sans `value`)

```json
{
  "id": "uuid...",
  "key_id": "prod-openai",
  "label": "OpenAI production",
  "provider": "openai",
  "harpo_path": "/vault-yoops/openai/prod-openai",
  "created_at": "2026-05-29T10:00:00Z"
}
```

### Providers disponibles

Pas de nouvel endpoint — le frontend déduit les providers distincts depuis la liste
de modèles existante `GET /api/admin/models` (table `model_dimensions`).

### Erreurs métier

- `409 Conflict` sur DELETE si `harpo_path` référencé dans un workspace
- `409 Conflict` sur POST si `(vault_id, provider, key_id)` déjà existant
- `422` si `key_id` ne respecte pas `^[a-zA-Z0-9_-]+$`
- `404` si `vault_id` ou `id` introuvable

---

## 4. Frontend

### Onglet "Apikeys" dans VaultDetailPanel

Nouveau 4ème onglet après "Info", clé i18n `tabs.apikeys`.

### VaultApikeysTab — liste

```
[+ Ajouter une clé]                              (bouton en haut à droite)

┌──────────────────┬──────────┬────────────────────┬──────────────┐
│ ID               │ Provider │ Label              │              │
├──────────────────┼──────────┼────────────────────┼──────────────┤
│ prod-openai      │ openai   │ OpenAI production  │ [↺] [×]      │
│ voyage-code      │ voyage   │ Voyage code        │ [↺] [×]      │
└──────────────────┴──────────┴────────────────────┴──────────────┘
```

- `[↺]` ouvre `ReplaceProviderKeyDialog` — champ password + confirm
- `[×]` ouvre un `AlertDialog` de confirmation ; bouton désactivé + tooltip si clé référencée
- Polling TanStack Query à la demande (pas de refetchInterval — les clés sont statiques)

### AddProviderKeyDialog — formulaire de création

```
Provider   [openai ▾]              ← <Select> peuplé depuis model_dimensions
Key ID     [prod-openai      ]     ← validation inline ^[a-zA-Z0-9_-]+$
Label      [OpenAI production]
Valeur     [sk-••••••••••••• ]     ← <Input type="password">
           Path : /vault-yoops/openai/prod-openai   ← preview calculé live
```

Le preview `harpo_path` se recalcule à chaque frappe sur `key_id` ou changement de provider.
Le bouton "Créer" est désactivé tant que `key_id` est invalide ou que la valeur est vide.

### ReplaceProviderKeyDialog

```
Remplacer la valeur de "prod-openai" (openai)
Nouvelle valeur  [sk-••••••••••••• ]
[Annuler]  [Remplacer]
```

### Fichiers

**Nouveaux :**
- `frontend/src/pages/harpocrate/VaultApikeysTab.tsx`
- `frontend/src/pages/harpocrate/AddProviderKeyDialog.tsx`
- `frontend/src/pages/harpocrate/ReplaceProviderKeyDialog.tsx`
- `backend/src/rag/schemas/provider_api_keys.py`
- `backend/src/rag/services/provider_api_keys.py`
- `backend/src/rag/api/admin_provider_keys.py`
- `backend/migrations/024_provider_api_keys.sql`
- `backend/tests/integration/test_migration_024.py`
- `backend/tests/integration/test_services_provider_api_keys.py`

**Modifiés :**
- `frontend/src/pages/harpocrate/VaultDetailPanel.tsx` — ajout onglet
- `frontend/src/lib/harpocrate-vaults.ts` — 4 méthodes API
- `frontend/src/lib/harpocrate-vaults.types.ts` — types ProviderApiKey*
- `frontend/src/i18n/fr/harpocrate.json` + `en/` — clés `apikeys.*`
- `backend/src/rag/main.py` — mount du nouveau router

---

## 5. Tests

### Backend

- `test_migration_024` : table créée, contrainte UNIQUE, ON DELETE RESTRICT
- `test_create_provider_key` : INSERT + push Harpocrate → 201
- `test_create_duplicate_key_id_409` : même (vault, provider, key_id) → 409
- `test_invalid_key_id_422` : key_id avec espace → 422
- `test_list_provider_keys` : GET retourne les clés sans valeur
- `test_patch_label` : PATCH label → label mis à jour en DB
- `test_patch_value` : PATCH value → valeur mise à jour dans Harpocrate
- `test_delete_unreferenced` : DELETE → 204, supprimé DB + Harpocrate
- `test_delete_referenced_409` : DELETE clé référencée → 409

### Frontend

- `VaultApikeysTab` : état vide, liste avec 2 clés
- `AddProviderKeyDialog` : validation key_id, preview path, bouton désactivé si invalide
