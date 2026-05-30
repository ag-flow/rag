# Design — Authentification Git par provider dans les sources

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Le dialog d'ajout/édition de source Git demande actuellement un coffre Harpocrate + un PAT saisi en clair. Ce chantier remplace ce flux par :
1. Sélection du provider Git (github/gitlab/gitea/bitbucket/azure-devops)
2. Choix du mode d'auth : Token (depuis `git_credentials`) OU Certificat SSH (depuis `ssh_keys`)
3. Credentials chargés depuis tous les vaults accessibles à l'utilisateur — pas de vault selector

Le clone SSH doit fonctionner dès la création de la config.

---

## Nouveaux endpoints backend

### `GET /api/admin/git-credentials/by-host?host=github`

Retourne les `git_credentials` des vaults accessibles au `current_owner` (is_default OU owner_id = current), filtrées par `host`.

**Response** : `list[GitCredentialWithVault]`
```
id           UUID
key_id       TEXT
label        TEXT
host         TEXT
harpo_path   TEXT    -- vault_ref utilisé comme auth_ref
vault_name   TEXT
vault_label  TEXT
created_at   datetime
```

### `GET /api/admin/ssh-keys/all`

Retourne toutes les `ssh_keys` des vaults accessibles au `current_owner`. Pas de filtre par type.

**Response** : `list[SshKeyWithVault]`
```
id                   UUID
key_id               TEXT
name                 TEXT
key_type             TEXT    -- ed25519 / rsa-4096 / ecdsa-256
public_key           TEXT
passphrase_protected BOOLEAN
harpo_path           TEXT    -- vault_ref utilisé comme ssh_key_ref
vault_name           TEXT
vault_label          TEXT
created_at           datetime
```

**Fichiers backend :**
- `backend/src/rag/schemas/git_credentials.py` — ajouter `GitCredentialWithVault`
- `backend/src/rag/schemas/ssh_keys.py` — ajouter `SshKeyWithVault`
- `backend/src/rag/services/git_credentials.py` — ajouter `list_git_credentials_by_host(conn, owner_id, host)`
- `backend/src/rag/services/ssh_keys.py` — ajouter `list_ssh_keys_for_owner(conn, owner_id)`
- `backend/src/rag/api/admin_git_credentials.py` — ajouter `router_global` + route `/by-host`
- `backend/src/rag/api/admin_ssh_keys.py` — ajouter `router_global` + route `/all`
- `backend/src/rag/main.py` — enregistrer les deux nouveaux routers

---

## Schémas de source

### `SourceCreateRequest` — nouveau

```python
class SourceCreateRequest(BaseModel):
    name: str
    type: Literal["git"]
    git_provider: str | None = None       # github | gitlab | gitea | bitbucket | azure-devops
    auth_type: Literal["token", "ssh"] | None = None
    auth_ref: str | None = None           # harpo_path du git_credential (token)
    ssh_key_ref: str | None = None        # harpo_path du ssh_key (SSH)
    ssh_username: str | None = None       # ex: "git" ; requis pour SSH gitea/azure-devops
    config: dict                           # {url, branch, include, exclude}
```

Suppression de `api_key_vault` et `auth_value` (plain text).

### `SourceUpdateRequest` — idem

Mêmes champs optionnels ajoutés.

### Stockage en DB

Les champs `git_provider`, `auth_type`, `auth_ref`, `ssh_key_ref`, `ssh_username` sont stockés dans le JSONB `sources.config`. Le service ne stocke plus rien dans Harpocrate (les credentials existent déjà).

---

## Support SSH dans `git_ops.py`

Deux nouvelles fonctions côté service qui complètent `clone` et `pull` :

**Logique SSH dans `clone` et `pull` :**

Quand `ssh_key` (str, contenu PEM de la clé privée) est fourni au lieu de `token` :

```python
import tempfile, os

with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
    f.write(ssh_key)
    tmp_key_path = f.name

os.chmod(tmp_key_path, 0o600)

env = {
    **os.environ,
    "GIT_SSH_COMMAND": (
        f"ssh -i {tmp_key_path} "
        "-o StrictHostKeyChecking=no "
        "-o BatchMode=yes"
    ),
    "GIT_TERMINAL_PROMPT": "0",
}

try:
    await _run_git([...], env=env)
finally:
    os.unlink(tmp_key_path)
```

L'URL SSH est passée sans modification (`git@github.com:org/repo.git`).

**Résolution de la clé** dans `services/sources.py` :

Avant le clone, si `config["auth_type"] == "ssh"` :
1. Résoudre `config["ssh_key_ref"]` via le `SecretResolver`
2. Passer la clé privée résolue + `config["ssh_username"]` à `git_ops.clone`

---

## Frontend

### Nouveaux types (`harpocrate-vaults.types.ts`)

```typescript
export type GitCredentialWithVault = {
  id: string;
  key_id: string;
  label: string;
  host: string;
  harpo_path: string;
  vault_name: string;
  vault_label: string;
  created_at: string;
};

export type SshKeyWithVault = {
  id: string;
  key_id: string;
  name: string;
  key_type: string;
  public_key: string;
  passphrase_protected: boolean;
  harpo_path: string;
  vault_name: string;
  vault_label: string;
  created_at: string;
};
```

### Nouveaux hooks

```typescript
useGitCredentialsByHost(host: string | null)   // GET /git-credentials/by-host?host=...
useSshKeysAll()                                 // GET /ssh-keys/all
```

### `AddSourceDialog.tsx` — refonte UX

**Champs :**
1. Nom de la source (create only)
2. URL du dépôt
3. Branche (optionnel)
4. **Provider** — Select : GitHub / GitLab / Gitea / Bitbucket / Azure DevOps
5. **Mode d'auth** — Radio : Token | Certificat SSH
6. Si Token : Select depuis `useGitCredentialsByHost(host)`
7. Si SSH : Select depuis `useSshKeysAll()` + Input Username (pré-rempli `"git"` sauf gitea/azure-devops)
8. Include / Exclude (csv)

**Règles username SSH :**
- github / gitlab / bitbucket → pré-rempli `"git"`, editable
- gitea / azure-devops → vide, champ visible et requis

**En mode édition :** provider et auth_type affichés en lecture seule ; le credential peut être changé.

### i18n nouvelles clés (namespace `workspace`)

```json
"sources.fields.git_provider": "Provider Git",
"sources.fields.auth_type": "Authentification",
"sources.fields.auth_type_token": "Token",
"sources.fields.auth_type_ssh": "Certificat SSH",
"sources.fields.credential": "Credential",
"sources.fields.credential_placeholder": "Sélectionner...",
"sources.fields.credential_none": "Aucun credential disponible pour ce provider",
"sources.fields.ssh_username": "Utilisateur SSH",
"sources.fields.ssh_username_placeholder": "git"
```

---

## Tests

### Backend
- `test_list_git_credentials_by_host` — filtre par host + owner
- `test_list_ssh_keys_for_owner` — retourne les clés owner + défaut
- `test_create_source_with_token_ref` — stocke auth_ref dans config, sans écriture Harpocrate
- `test_create_source_with_ssh_key_ref` — stocke ssh_key_ref + ssh_username dans config
- `test_git_ops_clone_ssh` — clone avec clé privée temp + GIT_SSH_COMMAND

---

## Périmètre hors-scope

- Vérification de la clé SSH passphrase (déchiffrement pas implémenté — les clés générées ne sont pas chiffrées)
- Support des URLs SSH custom (format git://)
- Changement du mode d'auth après création d'une source (l'existant est affiché en lecture)
