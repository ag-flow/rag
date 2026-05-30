# Design — Validité des clés API (expires_at)

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Les clés stockées dans l'onglet Apikeys d'un coffre Harpocrate (`provider_api_keys` et `git_credentials`) n'ont pas de durée de vie. Ce chantier ajoute un champ de validité facultatif : l'utilisateur saisit un nombre de jours, le backend calcule et stocke la date d'expiration. Valeur nulle = non-expirable.

Future évolution prévue mais hors scope : envoi de mails d'alerte à J-10.

---

## Base de données

### Migration 027 — `add_expires_at`

```sql
ALTER TABLE provider_api_keys ADD COLUMN expires_at TIMESTAMPTZ NULL;
ALTER TABLE git_credentials    ADD COLUMN expires_at TIMESTAMPTZ NULL;
```

- `NULL` = non-expirable (défaut pour les clés existantes).
- La date est calculée par le service Python : `now() + timedelta(days=valid_days)`.
- Lors d'un update avec nouveau `valid_days`, `expires_at` est recalculé depuis `now()` (pas depuis `created_at`).

---

## Backend

### Schemas

**`schemas/provider_api_keys.py`**

```
ProviderApiKeyCreate  : + valid_days: int | None  (Field ge=1, default=None)
ProviderApiKeyUpdate  : + valid_days: int | None  (Field ge=1, default=None)
ProviderApiKeyOut     : + expires_at: datetime | None
```

**`schemas/git_credentials.py`**

```
GitCredentialCreate   : + valid_days: int | None  (Field ge=1, default=None)
GitCredentialUpdate   : + valid_days: int | None  (Field ge=1, default=None)
GitCredentialOut      : + expires_at: datetime | None
```

### Services

**Création** (`create_provider_key`, `create_git_credential`) :

```python
from datetime import UTC, datetime, timedelta

expires_at = (
    datetime.now(UTC) + timedelta(days=req.valid_days)
    if req.valid_days is not None
    else None
)
```

`expires_at` passé dans l'`INSERT` ; présent dans le `RETURNING`.

**Mise à jour** (`update_provider_key`, `update_git_credential`) :

Si `req.valid_days is not None`, recalculer `expires_at = now() + timedelta(days=valid_days)`.
Si `req.valid_days is None`, conserver la valeur existante (`row["expires_at"]`).

Les requêtes `SELECT` et `UPDATE ... RETURNING` incluent `expires_at`.

---

## Frontend

### Types (`harpocrate-vaults.types.ts`)

```typescript
// Ajouts sur ProviderApiKey
expires_at: string | null;

// Ajouts sur ProviderApiKeyCreate / ProviderApiKeyUpdate
valid_days?: number | null;

// Ajouts sur GitCredential
expires_at: string | null;

// Ajouts sur GitCredentialCreate / GitCredentialUpdate
valid_days?: number | null;
```

### Dialogs

**`AddProviderKeyDialog` et `AddGitKeyDialog`** — nouveau champ optionnel :
- Label i18n : `apikeys.field_valid_days` / `gitkeys.field_valid_days`
- Input numérique (type `number`, min=1, step=1), placeholder `90`
- Texte d'aide : `apikeys.field_valid_days_help` → « Laisser vide = non-expirable »
- Soumis en `valid_days: validDays || null`

**`ReplaceProviderKeyDialog` et `ReplaceGitKeyDialog`** — même champ pour permettre de redéfinir l'expiration au remplacement.

### Table `VaultApikeysTab`

Nouvelle colonne dans chaque section :

| Section | Nouvelle colonne | Valeur si null |
|---|---|---|
| Clés LLM | `apikeys.col_expires_at` | `—` |
| Tokens Git | `gitkeys.col_expires_at` | `—` |

Affichage de la date : format `DD MMM YYYY` via `toLocaleDateString("fr-FR", {...})` ou helper `relativeDate` déjà utilisé dans le projet.

### i18n

Nouvelles clés dans le namespace `harpocrate` (fr + en) :

**FR :**
```json
"apikeys": {
  "col_expires_at": "Expire le",
  "field_valid_days": "Durée de validité (jours)",
  "field_valid_days_help": "Laisser vide pour une clé non-expirable"
}
"gitkeys": {
  "col_expires_at": "Expire le",
  "field_valid_days": "Durée de validité (jours)",
  "field_valid_days_help": "Laisser vide pour un token non-expirable"
}
```

**EN :**
```json
"apikeys": {
  "col_expires_at": "Expires on",
  "field_valid_days": "Validity (days)",
  "field_valid_days_help": "Leave empty for a non-expiring key"
}
"gitkeys": {
  "col_expires_at": "Expires on",
  "field_valid_days": "Validity (days)",
  "field_valid_days_help": "Leave empty for a non-expiring token"
}
```

---

## Périmètre hors-scope

- Alertes mail J-10 avant expiration (jalon ultérieur)
- Blocage ou avertissement visuel sur les clés expirées
- Badge « expire bientôt » dans les tables
