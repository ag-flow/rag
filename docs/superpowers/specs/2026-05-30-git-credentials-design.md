# Design — Git Credentials dans les coffres Harpocrate

**Date :** 2026-05-30
**Statut :** validé

## Contexte

L'onglet « Apikeys » d'un coffre Harpocrate permet déjà de stocker des clés API
pour les providers IA (OpenAI, Mistral, Jina, Voyage…) via la table
`provider_api_keys`. Les sources Git privées nécessitent des tokens d'accès
(GitHub PAT, GitLab PAT, Gitea token, etc.) qui doivent également être stockés
dans Harpocrate de façon sécurisée.

Ce chantier ajoute une section « Tokens Git » dans le même onglet, avec une
table dédiée et un dialog de création distinct.

---

## Base de données

### Migration 025 — `git_credentials`

```sql
CREATE TABLE git_credentials (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id     TEXT NOT NULL,
    label      TEXT NOT NULL,
    host       TEXT NOT NULL,
    scope_url  TEXT NULL,
    vault_id   UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, host, key_id)
);
```

**Champs :**
- `key_id` : identifiant court alphanumérique (`[a-zA-Z0-9_-]+`), ex: `prod-pat`
- `label` : description libre, ex: « GitHub org mycompany »
- `host` : valeur normalisée parmi `github | gitlab | gitea | bitbucket | azure-devops`
- `scope_url` : URL optionnelle purement organisationnelle, ex: `https://github.com/myorg`
- `harpo_path` : vault_ref complet `${vault://vault_name:/git/{host}/{key_id}}`

**Contrainte UNIQUE :** `(vault_id, host, key_id)` — même logique que `provider_api_keys`.

**Chemin Harpocrate :** `/git/{host}/{key_id}` — ex: `/git/github/prod-pat`.

---

## Backend

### Schemas — `schemas/git_credentials.py`

```
GitCredentialCreate   key_id, label, host, scope_url (opt), value
GitCredentialUpdate   label (opt), scope_url (opt), value (opt)
GitCredentialOut      id, key_id, label, host, scope_url, harpo_path, created_at
```

### Service — `services/git_credentials.py`

Fonctions autonomes (pas de classe), miroir de `services/provider_api_keys.py` :

| Fonction | Description |
|---|---|
| `list_git_credentials(conn, vault_id)` | Liste toutes les entrées du coffre |
| `create_git_credential(conn, vault, vault_svc, req)` | Écrit dans Harpocrate + INSERT ; rollback best-effort si UNIQUE violation |
| `update_git_credential(conn, key_id, vault, vault_svc, req)` | Met à jour label / scope_url / valeur Harpocrate |
| `delete_git_credential(conn, key_id, vault, vault_svc)` | Vérifie les références dans `sources.config->>'auth_ref'` avant suppression |

Chemin builder :
```python
def _build_secret_path(host: str, key_id: str) -> str:
    return f"/git/{host}/{key_id}"
```

### API — `api/admin_git_credentials.py`

Routes sous `/api/admin/harpocrate-vaults/{vault_id}/git-credentials` :

```
GET    /                    → list[GitCredentialOut]
POST   /                    → GitCredentialOut  (201)
PATCH  /{key_id}            → GitCredentialOut
DELETE /{key_id}            → 204
```

Erreurs :
- `409` si UNIQUE violation à la création
- `404` si vault ou credential introuvable
- `409` si référencé dans `sources.config->>'auth_ref'` à la suppression

Enregistrement dans `main.py` à côté du router `admin_provider_keys`.

---

## Frontend

### Nouveaux types — `harpocrate-vaults.types.ts`

```typescript
interface GitCredential {
  id: string;
  key_id: string;
  label: string;
  host: GitHost;
  scope_url: string | null;
  harpo_path: string;
  created_at: string;
}

type GitHost =
  | "github"
  | "gitlab"
  | "gitea"
  | "bitbucket"
  | "azure-devops";
```

### Nouvelles fonctions API — `harpocrate-vaults.ts`

```
listGitCredentials(vaultId)
createGitCredential(vaultId, payload)
updateGitCredential(vaultId, keyId, payload)
deleteGitCredential(vaultId, keyId)
```

### Nouveaux hooks — `useHarpocrateVaults.ts`

```
useGitCredentials(vaultId)
useCreateGitCredential(vaultId)
useUpdateGitCredential(vaultId)
useDeleteGitCredential(vaultId)
```

### Nouveaux composants

**`AddGitKeyDialog.tsx`**

Champs :
1. Host — Select fixe : GitHub / GitLab / Gitea / Bitbucket / Azure DevOps
2. Key ID — Input, validation `[a-zA-Z0-9_-]+`
3. Label — Input texte libre
4. Scope URL — Input optionnel (placeholder ex: `https://github.com/myorg`)
5. Valeur — Input password

Prévisualisation du chemin Harpocrate : `/git/{host}/{key_id}` (comme pour provider keys).

**`ReplaceGitKeyDialog.tsx`**

Même structure que `ReplaceProviderKeyDialog` : remplace uniquement la valeur
du token dans Harpocrate.

### `VaultApikeysTab.tsx` — mise à jour

Deux sections indépendantes dans le même onglet :

```
┌─────────────────────────────────────────────────────┐
│  Clés IA                          [ + Ajouter ]     │
│  ┌──────────────────────────────────────────────┐   │
│  │ key_id │ provider │ label │ actions          │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  Tokens Git                       [ + Ajouter ]     │
│  ┌──────────────────────────────────────────────┐   │
│  │ key_id │ host │ label │ scope_url │ actions  │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

Chaque section a son propre état `addOpen`, `toReplace`, `toDelete`.

### i18n

Nouvelles clés dans le namespace `harpocrate` (fr + en) :
```
gitkeys.section_title
gitkeys.add
gitkeys.empty
gitkeys.col_key_id
gitkeys.col_host
gitkeys.col_label
gitkeys.col_scope_url
gitkeys.add_dialog_title
gitkeys.field_host
gitkeys.field_key_id / field_key_id_help
gitkeys.field_label
gitkeys.field_scope_url / field_scope_url_placeholder
gitkeys.field_value
gitkeys.path_preview
gitkeys.created_toast / error_toast / error_duplicate
gitkeys.deleted_toast / delete_referenced_error
gitkeys.delete_confirm_title / delete_confirm_body
gitkeys.replace_dialog_title / replace_toast
gitkeys.cancel / save / delete_btn / replace_btn
```

---

## Tests

### Backend

- `test_git_credentials.py` — couverture CRUD complète :
  - create → liste → update label → replace value → delete
  - create avec UNIQUE violation → 409
  - delete référencé → 409
  - opérations sur vault inexistant → 404

### Frontend

- `AddGitKeyDialog.test.tsx` — validation formulaire + submit happy path
- `VaultApikeysTab` — les deux sections s'affichent

---

## Périmètre hors-scope

- Résolution automatique de clé Git par host lors de la création d'une source
- Support SSH (clé privée) — reporter à un jalon ultérieur
- Rotation de token Git (pourra être ajouté avec `ReplaceGitKeyDialog`)
