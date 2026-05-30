# Design — Onglet SSH dans les coffres Harpocrate

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Chaque coffre Harpocrate dispose d'un onglet « Apikeys » pour les clés LLM et les tokens Git. Ce chantier ajoute un onglet « SSH » permettant de gérer des paires de clés SSH : import (clé privée + publique) ou génération côté backend. La clé privée est chiffrée dans Harpocrate ; la clé publique, non-secrète, est stockée en DB pour un affichage sans appel Harpocrate.

Usage principal : déposer la clé publique sur GitHub/GitLab pour les clones SSH de sources privées.

---

## Base de données

### Migration 028

```sql
CREATE TABLE ssh_keys (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_id               TEXT NOT NULL,
    name                 TEXT NOT NULL,
    key_type             TEXT NOT NULL,
    public_key           TEXT NOT NULL,
    passphrase_protected BOOLEAN NOT NULL DEFAULT false,
    vault_id             UUID NOT NULL REFERENCES harpocrate_vaults(id) ON DELETE RESTRICT,
    harpo_path           TEXT NOT NULL,
    created_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vault_id, key_id)
);
```

**Champs :**
- `key_id` : slug alphanumérique (`[a-zA-Z0-9_-]+`), ex: `deploy-prod`
- `name` : libellé humain, ex: « Déploiement production »
- `key_type` : `ed25519` | `rsa-4096` | `ecdsa-256`
- `public_key` : clé publique OpenSSH complète, ex: `ssh-ed25519 AAAA...`
- `passphrase_protected` : `true` si la clé privée importée était chiffrée
- `harpo_path` : vault_ref complet `${vault://vault_name:/ssh/key_id/private_key}`

**Chemin Harpocrate :** `/ssh/{key_id}/private_key`

---

## Backend

### Dépendance

Ajouter `cryptography>=43.0` à `backend/pyproject.toml`. Utilisé pour :
- Générer Ed25519, RSA-4096, ECDSA-256
- Extraire la clé publique depuis une clé privée importée
- Sérialiser en format OpenSSH

### Schemas (`schemas/ssh_keys.py`)

```
SshKeyImport
    key_id        str  (slug, ^[a-zA-Z0-9_-]+$, max 64)
    name          str  (max 128)
    private_key   str  (contenu PEM/OpenSSH)
    public_key    str  (contenu OpenSSH)
    passphrase    str | None

SshKeyGenerate
    key_id        str  (slug, max 64)
    name          str  (max 128)
    key_type      Literal['ed25519', 'rsa-4096', 'ecdsa-256']

SshKeyOut
    id            UUID
    key_id        str
    name          str
    key_type      str
    public_key    str
    passphrase_protected  bool
    harpo_path    str
    created_at    datetime
```

### Service (`services/ssh_keys.py`)

Fonctions autonomes, miroir de `provider_api_keys` :

| Fonction | Description |
|---|---|
| `list_ssh_keys(conn, vault_id)` | Lecture DB, trié par `key_id` |
| `import_ssh_key(conn, vault, vault_svc, req)` | Stocke clé privée dans Harpocrate + clé publique en DB |
| `generate_ssh_key(conn, vault, vault_svc, req)` | Génère la paire via `cryptography`, stocke privée dans Harpocrate, publique en DB |
| `delete_ssh_key(conn, key_id, vault, vault_svc)` | Supprime dans Harpocrate + DB |

**Import** : la clé privée est stockée telle quelle dans Harpocrate. `passphrase_protected` est déduit de la présence d'une passphrase.

**Génération** :
- Ed25519 : `Ed25519PrivateKey.generate()`
- RSA-4096 : `rsa.generate_private_key(65537, 4096)`
- ECDSA-256 : `ec.generate_private_key(ec.SECP256R1())`
- Sérialisation clé privée : `OpenSSH` (format `-----BEGIN OPENSSH PRIVATE KEY-----`)
- Sérialisation clé publique : `OpenSSH` (`ssh-ed25519 AAAA...` / `ssh-rsa AAAA...` / `ecdsa-sha2-nistp256 AAAA...`)

**Exceptions** :
- `DuplicateSshKeyError` — UNIQUE violation
- `SshKeyNotFoundError` — clé introuvable

### API Router (`api/admin_ssh_keys.py`)

Routes sous `/api/admin/harpocrate-vaults/{vault_id}/ssh-keys` :

```
GET    /              → list[SshKeyOut]
POST   /import        → SshKeyOut  (201)
POST   /generate      → SshKeyOut  (201)
DELETE /{key_id}      → 204
```

Auth : `require_master_key_or_authenticated_admin` (comme les autres routers).
Erreurs : `404` vault absent, `409` UNIQUE violation, `204` suppression réussie.

---

## Frontend

### Onglet SSH dans `VaultDetailPanel.tsx`

Ajouter après l'onglet `apikeys` :
```tsx
<TabsTrigger value="ssh">{t("tabs.ssh")}</TabsTrigger>
// ...
<TabsContent value="ssh">
  <VaultSshTab vaultId={vault.id} />
</TabsContent>
```

### `VaultSshTab.tsx`

En-tête avec deux boutons :
- « Importer une clé » → ouvre `ImportSshKeyDialog`
- « Générer une clé » → ouvre `GenerateSshKeyDialog`

Tableau :

| Colonne | Contenu |
|---|---|
| ID | `key_id` (monospace) |
| Type | badge `ed25519` / `rsa-4096` / `ecdsa-256` |
| Nom | `name` |
| Clé publique | 30 premiers chars + `…` + bouton copie |
| Actions | Supprimer (avec AlertDialog de confirmation) |

État vide : « Aucune clé SSH configurée pour ce coffre. »

### `ImportSshKeyDialog.tsx`

Champs (fidèle au mockup) :
1. **Nom** — input texte
2. **ID (slug)** — input monospace, validation `[a-zA-Z0-9_-]+`
3. **Clé privée** — textarea + bouton upload fichier (`.pem`, `.key`, `id_*`)
4. **Clé publique** — textarea + bouton upload fichier (`.pub`)
5. **Passphrase** — input password, optionnel
6. Prévisualisation du chemin Harpocrate : `/ssh/{key_id}/private_key`

### `GenerateSshKeyDialog.tsx`

Champs :
1. **Nom** — input texte
2. **ID (slug)** — input monospace
3. **Type** — Select : Ed25519 / RSA-4096 / ECDSA-256

Après génération réussie : affiche la clé publique dans un textarea readonly avec bouton « Copier la clé publique » — message d'aide « Collez cette clé dans les paramètres SSH de GitHub / GitLab ».

### Types (`harpocrate-vaults.types.ts`)

```typescript
export type SshKeyType = 'ed25519' | 'rsa-4096' | 'ecdsa-256';

export type SshKey = {
  id: string;
  key_id: string;
  name: string;
  key_type: SshKeyType;
  public_key: string;
  passphrase_protected: boolean;
  harpo_path: string;
  created_at: string;
};

export type SshKeyImport = {
  key_id: string;
  name: string;
  private_key: string;
  public_key: string;
  passphrase?: string | null;
};

export type SshKeyGenerate = {
  key_id: string;
  name: string;
  key_type: SshKeyType;
};
```

### API client (`harpocrate-vaults.ts`)

```typescript
listSshKeys(vaultId)
importSshKey(vaultId, payload: SshKeyImport)
generateSshKey(vaultId, payload: SshKeyGenerate)
deleteSshKey(vaultId, keyId)
```

### Hooks (`useHarpocrateVaults.ts`)

```typescript
useSshKeys(vaultId)
useImportSshKey(vaultId)
useGenerateSshKey(vaultId)
useDeleteSshKey(vaultId)
```

### i18n (namespace `harpocrate`)

Nouveau bloc `ssh` en FR et EN :

**FR :**
```json
"ssh": {
  "tab": "SSH",
  "import_btn": "Importer une clé",
  "generate_btn": "Générer une clé",
  "empty": "Aucune clé SSH configurée pour ce coffre.",
  "col_key_id": "ID",
  "col_type": "Type",
  "col_name": "Nom",
  "col_public_key": "Clé publique",
  "delete_btn": "Supprimer",
  "delete_confirm_title": "Supprimer cette clé SSH ?",
  "delete_confirm_body": "La clé privée sera supprimée dans Harpocrate. Action irréversible.",
  "deleted_toast": "Clé SSH supprimée.",
  "import_dialog_title": "Importer une clé SSH",
  "import_dialog_subtitle": "Importez un fichier de clé privée existant (.pem, .key, id_rsa, id_ed25519).",
  "field_name": "Nom",
  "field_key_id": "ID (slug)",
  "field_key_id_help": "Lettres, chiffres, - et _ uniquement",
  "field_private_key": "Clé privée",
  "field_public_key": "Clé publique",
  "field_passphrase": "Passphrase",
  "field_passphrase_placeholder": "Optionnel",
  "choose_file": "Choisir un fichier",
  "path_preview": "Path Harpocrate :",
  "import_btn_submit": "Importer",
  "generate_dialog_title": "Générer une paire de clés SSH",
  "field_key_type": "Type de clé",
  "generate_btn_submit": "Générer",
  "generated_public_key_title": "Clé publique générée",
  "generated_public_key_help": "Collez cette clé dans les paramètres SSH de GitHub / GitLab.",
  "copy_public_key": "Copier la clé publique",
  "copied_toast": "Clé publique copiée.",
  "cancel": "Annuler",
  "close": "Fermer",
  "error_toast": "Une erreur est survenue.",
  "error_duplicate": "Un ID identique existe déjà pour ce coffre."
}
```

**EN :** traduction symétrique.

---

## Tests

### Backend

`tests/integration/test_services_ssh_keys.py` :
- `test_import_and_list` — import, vérifier `public_key` en DB et chemin Harpocrate
- `test_generate_ed25519` — clé publique valide `ssh-ed25519 AAAA…`
- `test_generate_rsa4096` — clé publique valide `ssh-rsa AAAA…`
- `test_generate_ecdsa256` — clé publique valide `ecdsa-sha2-nistp256 AAAA…`
- `test_duplicate_key_id_raises` — UNIQUE violation → `DuplicateSshKeyError`
- `test_delete_ssh_key` — suppression Harpocrate + DB

---

## Périmètre hors-scope

- Passphrase à la génération (les clés générées ne sont pas chiffrées côté Harpocrate)
- Rotation de clé SSH
- Révocation / liste de confiance
- Utilisation automatique des clés SSH dans les sources (jalon ultérieur)
