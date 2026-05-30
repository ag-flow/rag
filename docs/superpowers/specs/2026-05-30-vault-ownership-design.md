# Design — Vault Ownership (owner_id sur harpocrate_vaults)

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Les coffres Harpocrate sont actuellement globaux : tous les admins voient et peuvent modifier tous les coffres. Ce chantier ajoute un champ `owner_id` permettant de filtrer les coffres par propriétaire. Le coffre par défaut (`is_default = true`) fait office de coffre système, visible de tous.

**Prérequis DB** : remise à zéro de la base (pas de migration des données existantes).

---

## Base de données

### Migration 029

```sql
-- Migration 029 — ownership des coffres Harpocrate

ALTER TABLE harpocrate_vaults ADD COLUMN owner_id TEXT NOT NULL;
CREATE INDEX harpocrate_vaults_owner ON harpocrate_vaults (owner_id);
```

`owner_id = sha256(email.lower())` — calculé côté service Python.

---

## Backend

### Calcul du owner_id

Nouvelle fonction utilitaire dans `auth/owner.py` :

```python
import hashlib

def email_to_owner_id(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()
```

Source de l'email selon le mode d'authentification :
- **Session OIDC** : claim `email` du token JWT (via `request.session`)
- **Master key** : `settings.RAG_BOOTSTRAP_ADMIN_EMAIL`

Nouvelle dépendance FastAPI `get_current_owner_id(request) -> str` injectée dans les routes de vault.

### Règles d'accès

| Opération | Condition |
|---|---|
| `GET /harpocrate-vaults` (liste) | `is_default = true` OU `owner_id = current` |
| `POST /harpocrate-vaults` | `owner_id` forcé à `current` |
| `GET /harpocrate-vaults/{id}` | `is_default = true` OU `owner_id = current` |
| `PATCH /harpocrate-vaults/{id}` | `owner_id = current` uniquement |
| `DELETE /harpocrate-vaults/{id}` | `owner_id = current` uniquement |
| Sous-routes (`/provider-keys`, `/git-credentials`, `/ssh-keys`) | héritent de la règle GET du vault parent |

### Service `harpocrate_vaults`

Modifier :
- `list_all(conn)` → `list_for_owner(conn, owner_id: str)` : `WHERE is_default OR owner_id = $1`
- `create(conn, req, owner_id)` : ajoute `owner_id` à l'INSERT
- `get_by_id(conn, vault_id)` → retourne le vault sans filtre owner (le router applique le filtre)

### Router `admin_harpocrate_vaults`

- Injecter `owner_id = get_current_owner_id(request)` dans chaque route
- Liste : passer `owner_id` au service
- Create : passer `owner_id` au service
- Get/Patch/Delete : vérifier `vault.owner_id == owner_id OR vault.is_default` (sauf PATCH/DELETE : `owner_id` uniquement)

---

## Frontend

Aucun changement frontend nécessaire — le filtrage est transparent (la liste retournée par le backend est déjà filtrée).

---

## Tests

- `test_create_sets_owner_id` — vault créé, owner_id = sha256(email)
- `test_list_filters_by_owner` — user A ne voit pas les vaults de user B (sauf défaut)
- `test_default_vault_visible_to_all` — le vault par défaut est retourné pour tout owner
- `test_patch_forbidden_for_non_owner` — 403 si owner_id ne correspond pas

---

## Périmètre hors-scope

- UI d'administration pour transférer l'ownership d'un vault
- Notion de super-admin qui voit tous les vaults
