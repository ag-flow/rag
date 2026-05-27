# M5e — Workspace api_key chiffrée (pgcrypto) + endpoint GET idempotent

> **Statut** : design validé pour implémentation TDD.
> **Spec produit ciblée** : `specs/08-docker-init.md`.
> **Prérequis** : M5c (`pgcrypto` activé, pattern `pgp_sym_encrypt/decrypt`).

## 1. Contexte et motivation

La spec 08 décrit un script `init-rag.sh` qui, au démarrage d'un container agent
ag.flow, appelle un endpoint **idempotent** retournant l'api_key d'un workspace :

> « L'endpoint `GET /workspaces/{name}/apikey` retourne toujours la même clé pour
> un workspace donné. »

Le modèle actuel stocke `workspaces.api_key_hash` en **bcrypt** (cf.
`backend/src/rag/services/apikey.py`), donc la clé en clair est non récupérable
après création. La spec 08 est inapplicable en l'état.

Le pattern de référence dans le repo est celui des coffres Harpocrate
(`backend/src/rag/services/harpocrate_vaults.py:57,67,82`) :

- colonne `api_key_encrypted BYTEA` chiffrée via `pgp_sym_encrypt(value, dek)::bytea`
- décryptage SQL-side `pgp_sym_decrypt(col, dek)`
- DEK ≥ 32 caractères, validé au démarrage

Ce jalon **réplique ce pattern** pour les api_keys workspace, débloque la
spec 08, et homogénéise la stratégie de chiffrement réversible côté serveur.

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Chiffrement réversible pgcrypto, **pas** bcrypt | Spec 08 exige idempotence (« toujours la même clé ») |
| D2 | Nouvelle variable d'env dédiée `RAG_API_KEY_DEK` | Séparation des préoccupations vs `HARPOCRATE_DEK` |
| D3 | Pas de stratégie de migration de données | Table `workspaces` vide en BDD test (0 row confirmé) |
| D4 | Path endpoint : `/api/admin/workspaces/{name}/apikey` | Cohérence avec le préfixe admin du repo ; spec 08 mise à jour |
| D5 | Auth : `require_master_key_or_oidc_role("rag-admin")` | Dépendance déjà existante (`auth/bearer.py`) — supporte Bearer master key (init-rag.sh) ET OIDC (UI) |
| D6 | Lookup workspace par **fingerprint SHA-256** | `pgp_sym_encrypt` non-déterministe → impossible de matcher la valeur chiffrée. Le fingerprint donne O(1) sur index unique |
| D7 | Chiffrement / déchiffrement **SQL-side** | Cohérent avec `harpocrate_vaults.py` ; pas de helper Python à maintenir |
| D8 | Rotation de DEK : hors scope | À traiter dans un jalon dédié si besoin opérationnel |

## 3. Schéma BDD

### 3.1 Migration `010_workspace_apikey_encrypted.sql`

```sql
-- Migration 010 — workspace.api_key : bcrypt → pgcrypto (chiffrement réversible)
--
-- Préconditions : table workspaces vide (0 row).
-- L'extension pgcrypto est déjà activée par la migration 009.

ALTER TABLE workspaces DROP COLUMN api_key_hash;

ALTER TABLE workspaces
    ADD COLUMN api_key_encrypted BYTEA NOT NULL,
    ADD COLUMN api_key_fingerprint TEXT NOT NULL;

CREATE UNIQUE INDEX idx_workspaces_apikey_fingerprint
    ON workspaces (api_key_fingerprint);
```

### 3.2 Invariants

- `api_key_encrypted` : `pgp_sym_encrypt(<api_key_clear>, $RAG_API_KEY_DEK)::bytea`
- `api_key_fingerprint` : `encode(digest(<api_key_clear>, 'sha256'), 'hex')`
- L'index `UNIQUE` sur `api_key_fingerprint` détecte les collisions (probabilité ~2⁻¹²⁸ par paire ; le service régénère en cas de conflit).

## 4. Configuration

### 4.1 `backend/src/rag/config.py`

Ajout d'un champ Pydantic Settings :

```python
api_key_dek: str | None = Field(default=None, alias="RAG_API_KEY_DEK")

@field_validator("api_key_dek")
@classmethod
def _validate_api_key_dek(cls, v: str | None) -> str | None:
    # Une valeur vide (RAG_API_KEY_DEK= dans .env) est traitée comme absente.
    if not v:
        return None
    if len(v) < 32:
        raise ValueError("RAG_API_KEY_DEK doit faire au moins 32 caractères")
    return v
```

### 4.2 `.env.example`

```
# Clé maître de chiffrement réversible des api_keys workspace.
# DOIT faire au moins 32 caractères. ATTENTION : perdre cette valeur
# rend toutes les api_keys workspace inutilisables (réindexation manuelle requise).
# Indépendant de HARPOCRATE_DEK.
RAG_API_KEY_DEK=
```

### 4.3 Lifespan

Au démarrage (lifespan FastAPI, après création du pool) :

```python
async with pool.acquire() as conn:
    count = await conn.fetchval("SELECT COUNT(*) FROM workspaces")
if count > 0 and settings.api_key_dek is None:
    raise RuntimeError(
        "RAG_API_KEY_DEK manquant alors que la table workspaces est non vide"
    )
```

## 5. Service `apikey.py`

### 5.1 Avant (à supprimer)

- `hash_api_key(key: str) -> str` (bcrypt)
- `verify_api_key(provided: str, stored_hash: str) -> bool` (bcrypt)
- Constantes `_BCRYPT_ROUNDS`, import `bcrypt`

### 5.2 Après (à conserver)

- `generate_api_key() -> str` : inchangé (48 chars base64-url, 36 bytes d'entropie)

Le chiffrement / déchiffrement / fingerprint **ne nécessitent aucun helper
Python** — ils sont exprimés directement dans les requêtes SQL des services
`workspaces.py` et `auth/workspace_auth.py`.

## 6. Endpoints API

### 6.1 Nouveau — `GET /api/admin/workspaces/{name}/apikey`

```python
@router.get("/workspaces/{name}/apikey")
async def get_apikey_endpoint(name: str, request: Request) -> ApiKeyRotateResponse:
    dek = request.app.state.settings.api_key_dek
    if dek is None:
        raise HTTPException(503, "api_key_dek_unavailable")
    row = await request.app.state.config_pool.fetchrow(
        "SELECT pgp_sym_decrypt(api_key_encrypted, $2::text)::text AS api_key "
        "FROM workspaces WHERE name = $1",
        name, dek,
    )
    if row is None:
        raise HTTPException(404, "workspace_not_found")
    return ApiKeyRotateResponse(api_key=row["api_key"])
```

- Auth via `require_master_key_or_oidc_role("rag-admin")` (héritée du router).
- Idempotent par construction.
- Réutilise `ApiKeyRotateResponse` existant pour homogénéité.

### 6.2 Refactor — `POST /api/admin/workspaces` (création)

INSERT modifié :

```sql
INSERT INTO workspaces (name, ..., api_key_encrypted, api_key_fingerprint)
VALUES (
    $1, ...,
    pgp_sym_encrypt($N::text, $K::text)::bytea,
    encode(digest($N::text, 'sha256'), 'hex')
)
```

Réponse inchangée : la clé en clair est renvoyée à la création.

### 6.3 Refactor — `POST /api/admin/workspaces/{name}/rotate-apikey`

UPDATE modifié :

```sql
UPDATE workspaces
SET api_key_encrypted = pgp_sym_encrypt($2::text, $3::text)::bytea,
    api_key_fingerprint = encode(digest($2::text, 'sha256'), 'hex')
WHERE name = $1
```

Boucle de régénération côté service en cas de violation UNIQUE
(`asyncpg.UniqueViolationError`), bornée à **3 tentatives** puis remontée
de l'erreur — proba ~2⁻¹²⁸ par paire, défense en profondeur.

## 7. Workspace auth (`auth/workspace_auth.py`)

### 7.1 Stratégie

L'auth workspace reçoit un Bearer `<api_key>`. Le workflow devient :

1. Calculer `fingerprint = sha256_hex(provided_key)` (côté Python, `hashlib`).
2. `SELECT name, pgp_sym_decrypt(api_key_encrypted, $2::text)::text AS stored
   FROM workspaces WHERE api_key_fingerprint = $1` — O(1) sur index unique.
3. Si `row is None` → 401.
4. Comparer `provided_key` et `stored` via `secrets.compare_digest` (timing-safe).
5. Si match → renvoyer `AuthContext(workspace_name=row["name"])`.

### 7.2 Justification du double check

Le fingerprint suffit à identifier le workspace, mais on **décrypte et compare**
en plus pour garantir qu'aucune collision SHA-256 (improbable mais théorique)
ne valide une fausse clé. Coût : 1 décrypt par requête authentifiée.

## 8. Plan de tests TDD

| # | Fichier | Cas couverts |
|---|---|---|
| T1 | `tests/integration/db/test_workspace_apikey_crypto.py` | Round-trip `pgp_sym_encrypt`/`pgp_sym_decrypt`, fingerprint déterministe, contrainte UNIQUE sur fingerprint |
| T2 | `tests/unit/test_config_api_key_dek.py` | Validateur Settings : vide → None, < 32 → ValueError, ≥ 32 → OK |
| T3 | `tests/unit/services/test_apikey.py` | `generate_api_key()` : longueur, charset, entropie ; suppression des tests bcrypt |
| T4 | `tests/integration/api/test_admin_workspaces_apikey.py` | • GET 200 retourne clé stockée<br>• GET idempotent (2 appels = même valeur)<br>• GET 404 workspace inexistant<br>• GET 401 sans bearer<br>• GET 503 si DEK absent<br>• POST rotate → GET reflète la nouvelle valeur<br>• POST workspaces : INSERT crée fingerprint + encrypted |
| T5 | `tests/integration/auth/test_workspace_apikey_lookup.py` | • `require_workspace_apikey` valide une clé existante via fingerprint + decrypt<br>• Rejette une clé inconnue (401)<br>• Rejette une clé expirée après rotate (l'ancienne ne match plus) |
| T6 | `tests/integration/test_lifespan_dek_required.py` | Workspaces non vide + `RAG_API_KEY_DEK` absent → `RuntimeError` au startup |

## 9. Ordre d'exécution

1. **Migration** `010_workspace_apikey_encrypted.sql` + tests T1
2. **Config** : `api_key_dek` + validateur + tests T2
3. **Service apikey.py** : suppression bcrypt, conservation `generate_api_key` + tests T3
4. **Service workspaces.create** : INSERT chiffré + fingerprint + tests intégration (subset T4)
5. **Service rotate_apikey** : UPDATE chiffré + fingerprint + boucle anti-collision + tests intégration (subset T4)
6. **`auth/workspace_auth.py`** : lookup fingerprint + decrypt + compare timing-safe + tests T5
7. **Endpoint nouveau** `GET /workspaces/{name}/apikey` + tests T4 (GET dédiés)
8. **Lifespan** : check DEK requis si workspaces non vide + tests T6
9. **`.env.example`** : doc `RAG_API_KEY_DEK`
10. **Spec 08** : mise à jour du path (`/api/admin/...`) et note DEK requis côté serveur
11. **Smoke E2E manuel** sur LXC 303 : déploiement + create workspace + GET apikey via Bearer master

Chaque tâche : test rouge → impl → test vert → commit conventionnel français.

## 10. Risques et hors-scope

| Risque | Mitigation |
|---|---|
| Perte de la DEK = clés inutilisables | Doc explicite dans `.env.example` ; secret en gestion externe |
| Collision SHA-256 sur fingerprint | Index UNIQUE + boucle régénération |
| Tests existants liés à bcrypt | Grep + adaptation dans la tâche correspondante |
| Coût décrypt à chaque auth workspace | 1 décrypt SQL-side par requête authentifiée, négligeable jusqu'à ~10k workspaces |

**Hors-scope explicite** :

- Rotation de `RAG_API_KEY_DEK` (re-chiffrement de masse).
- Audit log des appels `GET /apikey`.
- Rate limiting de l'endpoint GET.
- Script `init-rag.sh` lui-même (vit dans le repo `ag.flow.docker`, pas ici).

## 11. Cohérence spec 08

À l'issue de ce jalon, modifier `specs/08-docker-init.md` :

- Path : `GET /workspaces/{name}/apikey` → `GET /api/admin/workspaces/{name}/apikey`
- Ajouter note serveur : « Le service RAG doit définir `RAG_API_KEY_DEK` (≥ 32 chars) pour activer la résolution. »
- Conserver la sémantique idempotente du contrat.
