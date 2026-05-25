# Consolidation workspace api_keys dans Harpocrate — design

**Date** : 2026-05-21
**Statut** : design, en attente de revue
**Auteur** : architecte (brainstorm)

## 1. Contexte

Aujourd'hui le projet a deux mécanismes de protection des secrets DB qui se
chevauchent :

- **`HARPOCRATE_DEK`** chiffre les api_keys des coffres Harpocrate eux-mêmes
  (table `harpocrate_vaults.api_key_encrypted`). C'est la "clé qui sécurise les
  clés qui débloquent les autres secrets" — le pivot central.
- **`RAG_API_KEY_DEK`** chiffre les api_keys MCP des workspaces directement
  via `pgcrypto pgp_sym_encrypt` dans `workspaces.api_key_encrypted`. Mécanisme
  parallèle à Harpocrate, hérité de l'implémentation M5e.

Cette dualité a deux conséquences :

1. **Conceptuellement** : Harpocrate est le coffre désigné pour tous les
   secrets ; les api_keys workspace devraient y vivre aussi.
2. **Opérationnellement** : deux SPOF distincts (perdre `RAG_API_KEY_DEK` rend
   toutes les api_keys workspace inutilisables ; perdre `HARPOCRATE_DEK` rend
   tous les coffres inutilisables) au lieu d'un seul.

## 2. Objectif

Supprimer `RAG_API_KEY_DEK` en migrant les api_keys MCP workspace vers un
stockage Harpocrate explicite. La clé fondamentale unique du projet devient
`HARPOCRATE_DEK`.

Le formalisme de référence reste `${vault://<vault_name>:<path>}` (les deux
parties sont obligatoires, cf. `backend/src/rag/secrets/refs.py:5`).

## 3. Cadrage et décisions

| Décision | Choix retenu | Justification |
|---|---|---|
| Stratégie de migration des données | **Greenfield** (DB recréée from scratch) | L'opérateur a explicitement validé ce choix. Pas de portage de données à coder. |
| Granularité Harpocrate | Le coffre cible est **spécifié explicitement** au POST workspace (champ `api_key_vault`) | Cohérent avec le formalisme strict `${vault://<vault>:<path>}` où le coffre n'est pas optionnel. Pas de magie "coffre par défaut" pour les workspaces. |
| Convention de path | `wsapi_<workspace_name>` | Dérivé automatiquement du nom du workspace (immuable de facto, car `rag_<name>` est le nom de la DB pgvector). Pas de saisie utilisateur supplémentaire. |
| Stockage en DB | `workspaces.api_key_ref TEXT NOT NULL` contenant la string complète `${vault://<vault>:wsapi_<name>}` | Pattern aligné sur `parse_ref` / `build_ref` existants. Lookup direct sans concat à la volée. |
| Lookup fingerprint | Conservation de `workspaces.api_key_fingerprint TEXT` | Lookup O(1) par SHA-256 du bearer reçu. Sans fingerprint, il faudrait résoudre toutes les api_keys via Harpocrate à chaque requête (catastrophe perf). |
| Cache des api_keys résolues | **Process-lifetime**, sans TTL, invalidation explicite à la rotation | Le user a validé : "le service tourne, optimise jusqu'à l'arrêt, puis on relit la clé". Pas de pré-warm au boot. |
| Comportement Harpocrate down | **Fail rapide 503** + cache process-lifetime absorbe les pannes courtes | SPOF Harpocrate connu et accepté. Une fois la clé en cache, le workspace continue à fonctionner même si Harpocrate tombe. |
| OIDC, rerank, indexer | **Inchangés** (résolution via coffre par défaut) | Hors-scope de ce jalon. Refactor possible séparément. |

## 4. Architecture

### 4.1 Flow auth MCP — avant / après

**Avant** :

```
Agent externe                Backend                       DB
   │ Bearer <api_key>           │                            │
   │──────────────────────────► │                            │
   │                            │ SHA-256(bearer) = fp        │
   │                            │ lookup WHERE fp = ?         │
   │                            │──────────────────────────► │
   │                            │ ◄─ encrypted_blob ─────────│
   │                            │ pgp_sym_decrypt(blob,       │
   │                            │   RAG_API_KEY_DEK)          │
   │                            │ compare timing-safe         │
   │ ◄─── 200/401 ──────────────│                            │
```

**Après** :

```
Agent externe        Backend         Cache         Harpocrate         DB
   │ Bearer <api_key>   │              │              │                │
   │──────────────────► │              │              │                │
   │              SHA-256(bearer) = fp                                  │
   │                    │ lookup fp ──────────────────────────────────► │
   │                    │◄── row {workspace_id, api_key_ref} ───────────│
   │                    │ get(api_key_ref) │              │              │
   │                    │─────────────────► │              │              │
   │                    │           ┌──── miss            │              │
   │                    │           │ resolve(api_key_ref)│              │
   │                    │           │─────────────────────► │            │
   │                    │           │◄── api_key clair ─────│            │
   │                    │           └─► cache (lifetime)                │
   │                    │◄── api_key clair ─                              │
   │                    │ compare timing-safe (bearer vs clair)          │
   │ ◄─── 200/401 ──────│                                                │
```

### 4.2 Pré-requis runtime

- Au moins un coffre Harpocrate dans `harpocrate_vaults` doit exister avant
  le premier `POST /api/admin/workspaces`. Sinon → 400 `vault_not_found`.
- Au boot du backend : si `workspaces` est non-vide ET aucun coffre n'existe
  → `RuntimeError` explicite (état incohérent).

### 4.3 Composants nouveaux ou modifiés

- **DB** : migration `015_workspaces_apikey_ref.sql` (DROP `api_key_encrypted`,
  ADD `api_key_ref TEXT NOT NULL`).
- **Settings** : retire `api_key_dek` (+ alias `RAG_API_KEY_DEK`) + son
  validateur.
- **`.env.example`** : retire le bloc `RAG_API_KEY_DEK`.
- **Schémas** : ajoute `api_key_vault: str` à `WorkspaceCreateRequest`.
- **Services** : `create_workspace`, `rotate_apikey` refactorés (lecture/écriture
  Harpocrate au lieu de pgcrypto).
- **Auth** : `require_workspace_apikey` lit par fingerprint + résout via cache
  process-lifetime + `SecretResolver`.
- **Cache** : `ApiKeyCache` refactor (process-lifetime, plus de TTL,
  invalidation explicite).
- **Erreurs typées** : `VaultNotFoundForWorkspace`, `HarpocrateWriteFailed`,
  `HarpocrateUnreachableForApikey`.

## 5. Composants backend

### 5.1 Migration `015_workspaces_apikey_ref.sql`

```sql
-- Migration 015 — workspaces : api_key_encrypted → api_key_ref (Harpocrate)
-- Greenfield : la DB est recréée from scratch (workspaces table vide).
ALTER TABLE workspaces
    DROP COLUMN api_key_encrypted,
    ADD COLUMN api_key_ref TEXT NOT NULL;
-- api_key_fingerprint conservé (lookup O(1) bearer auth).
```

Pas de `DEFAULT` sur `api_key_ref` : si la table n'est pas vide au moment de
la migration, l'ADD COLUMN NOT NULL échoue. C'est intentionnel — un état
greenfield est exigé.

### 5.2 Settings (`backend/src/rag/config.py`)

Retirer :
- Le champ `api_key_dek: str | None = Field(default=None, alias="RAG_API_KEY_DEK")`.
- Le `field_validator` `_validate_api_key_dek`.
- L'utilisation côté lifespan (le check "api_key_dek requis si table non vide"
  disparaît avec le champ).

### 5.3 Schéma `WorkspaceCreateRequest`

```python
class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., pattern=...)  # existant
    api_key_vault: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Nom du coffre Harpocrate où sera stockée l'api_key MCP",
    )
    indexer: IndexerConfigCreate
    # ... autres champs existants
```

### 5.4 Service `create_workspace`

Refactor `backend/src/rag/services/workspaces.py:create_workspace`. Nouvelle
signature (sans `api_key_dek`, avec `harpocrate_vaults_service`) :

```python
async def create_workspace(
    *,
    request: WorkspaceCreateRequest,
    config_pool: asyncpg.Pool,
    admin_dsn: str,
    resolver: _ResolverProtocol,
    harpocrate_vaults_service: HarpocrateVaultsService,
) -> dict[str, str]:
    """Crée un workspace + sa base pgvector + sa table embeddings.

    Étapes :
      1. Lookup dimension model_dimensions.
      2. Vérifie que le coffre `request.api_key_vault` existe.
      3. Eager validation de indexer.api_key_ref via Harpocrate (existant).
      4. Génère api_key + fingerprint SHA-256 + path = wsapi_<name>.
      5. Écrit la clé dans Harpocrate AVANT l'INSERT DB.
      6. INSERT workspaces (api_key_ref string complète + fingerprint) +
         indexer_configs + chunking_configs (TRANSACTION).
      7. CREATE DATABASE rag_<name> (admin_dsn, hors transaction).
      8. Migrations workspace schema.
      9. Retour {id, name, api_key, created_at} — api_key en clair UNIQUE.

    Compensations :
      - Si étape 6 échoue → DELETE secret Harpocrate (best-effort, log si fail).
      - Si étapes 7-8 échouent → DELETE workspaces + DROP DATABASE + DELETE
        secret Harpocrate.
    """
```

L'ordre **écriture Harpocrate AVANT INSERT DB** est délibéré : si l'INSERT
échoue (ex. unique violation sur `name`), on rollback proprement le secret
Harpocrate. L'inverse laisserait une row DB pointant vers une ref inexistante,
puis échec à la première requête MCP.

### 5.5 Service `rotate_apikey`

`backend/src/rag/services/workspaces.py:rotate_workspace_apikey` (à refactorer
de la même façon). Étapes :

1. Lit `api_key_ref` du workspace.
2. Génère nouvelle api_key + nouveau fingerprint.
3. Update Harpocrate sous le même `api_key_ref` (write idempotent).
4. Update `workspaces.api_key_fingerprint` en DB.
5. **`apikey_cache.invalidate(api_key_ref)`** — critique pour éviter le clair
   stale en mémoire.
6. Retourne la nouvelle api_key (one-shot).

Compensation : si étape 4 échoue après étape 3, on tente une re-rotation
Harpocrate à la valeur précédente (best-effort, log si échec).

### 5.6 Auth `require_workspace_apikey`

`backend/src/rag/auth/workspace_auth.py`. Nouvelle implémentation :

```python
async def require_workspace_apikey(name: str, request: Request) -> AuthContext:
    api_key = _extract_bearer(request)
    fingerprint = sha256(api_key.encode()).hexdigest()

    pool = request.app.state.pools.config_pool
    row = await pool.fetchrow(
        """
        SELECT w.id, w.api_key_ref,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1 AND w.api_key_fingerprint = $2
        """,
        name, fingerprint,
    )
    if row is None:
        raise HTTPException(status_code=401, detail=...)  # uniform

    cache: ApiKeyCache = request.app.state.apikey_cache
    api_key_ref: str = row["api_key_ref"]
    cached = cache.get(api_key_ref)
    if cached is None:
        resolver: SecretResolver = request.app.state.resolver
        try:
            cached = await resolver.resolve_with_retry(api_key_ref)
        except VaultUnreachable as e:
            raise HarpocrateUnreachableForApikey() from e
        cache.put(api_key_ref, cached)

    if not hmac.compare_digest(cached, api_key):
        raise HTTPException(status_code=401, detail=...)

    return AuthContext(workspace_id=row["id"], indexer_used=row["indexer_used"])
```

### 5.7 Cache `ApiKeyCache`

Refactor `backend/src/rag/auth/workspace_auth.py:ApiKeyCache`. Nouvelle
interface (process-lifetime, plus de TTL) :

```python
class ApiKeyCache:
    """Cache mémoire process-lifetime des api_keys MCP résolues.

    Clé = api_key_ref (string `${vault://<vault>:<path>}`)
    Valeur = api_key en clair
    Pas de TTL : invalidation explicite à la rotation via `invalidate(ref)`.
    Cold au démarrage : aucune entrée préchargée.
    """

    def get(self, ref: str) -> str | None: ...
    def put(self, ref: str, value: str) -> None: ...
    def invalidate(self, ref: str) -> None: ...
```

L'ancienne API `get(name, api_key)` et l'usage de tuple `(workspace_name,
api_key_clair)` comme clé disparaissent — la clé devient le `api_key_ref`
seul.

### 5.8 Erreurs typées (`backend/src/rag/api/errors.py`)

Toutes extend `AdminError` :

| Exception | HTTP | error code | Message |
|---|---|---|---|
| `VaultNotFoundForWorkspace(vault_name)` | 400 | `vault_not_found` | "Le coffre Harpocrate '<vault_name>' n'existe pas. Créer le coffre via /ui/settings/harpocrate-vaults avant de créer un workspace." |
| `HarpocrateWriteFailed(reason)` | 502 | `harpocrate_write_failed` | "Échec écriture du secret côté Harpocrate : <reason>" |
| `HarpocrateUnreachableForApikey` | 503 | `harpocrate_unreachable` | "Harpocrate inaccessible pour résoudre l'api_key workspace." |

`VaultUnreachable` (existant) reste pour les autres call sites (resolution de
secrets non-workspace).

### 5.9 Routes admin et MCP

- `backend/src/rag/api/admin.py` (4 endpoints workspace : create, rotate,
  reveal, regenerate — selon l'API actuelle) : retirent le paramètre
  `api_key_dek` injecté, ajoutent `harpocrate_vaults_service`.
- `backend/src/rag/api/mcp.py` (3 endpoints) : retirent `api_key_dek`.
- L'endpoint `reveal-apikey` actuel (qui déchiffrait via DEK) doit lui aussi
  passer par le cache + resolver Harpocrate.

## 6. Data flow

### 6.1 Création workspace

```
Operator → POST /api/admin/workspaces {name, api_key_vault, indexer, ...}
   │
   ├─ get_by_name(api_key_vault) → présent ?
   │  └─ non → 400 vault_not_found
   ├─ generate_api_key() → clair + sha256 fingerprint
   ├─ build_ref(api_key_vault, "wsapi_<name>") → "${vault://X:wsapi_Y}"
   ├─ Harpocrate.write(vault, "wsapi_<name>", api_key_clair)
   │  └─ fail → 502 harpocrate_write_failed
   ├─ INSERT workspaces + indexer_configs + chunking_configs (TRANSACTION)
   │  └─ fail → DELETE secret Harpocrate (best-effort), propage l'erreur
   ├─ CREATE DATABASE rag_<name> + migrations workspace
   │  └─ fail → DELETE workspaces + DROP DATABASE + DELETE secret Harpocrate
   └─ 201 {id, name, api_key (clair, one-shot), created_at}
```

### 6.2 Auth MCP (chemin chaud)

```
GET /mcp/<name>/* avec Bearer <api_key>
   │
   ├─ fingerprint = sha256(bearer)
   ├─ SELECT w.id, w.api_key_ref, ic.provider/model
   │  FROM workspaces w JOIN indexer_configs ic
   │  WHERE w.name = ? AND w.api_key_fingerprint = ?
   │  └─ row None → 401 (uniform : ne révèle pas l'existence du workspace)
   ├─ cache.get(api_key_ref) ?
   │  ├─ hit → continue
   │  └─ miss → resolver.resolve_with_retry(api_key_ref)
   │      ├─ ok → cache.put(api_key_ref, clair) → continue
   │      └─ VaultUnreachable → 503 harpocrate_unreachable
   ├─ compare_digest(cache_value, bearer) ?
   │  └─ false → 401 (uniform)
   └─ 200 + AuthContext(workspace_id, indexer_used)
```

### 6.3 Rotation api_key

```
POST /api/admin/workspaces/<name>/rotate-apikey
   │
   ├─ SELECT api_key_ref FROM workspaces WHERE name = ?
   ├─ generate_api_key() → nouveau clair + nouveau fingerprint
   ├─ Harpocrate.write(vault, "wsapi_<name>", nouveau_clair)  (idempotent upsert)
   │  └─ fail → 502, pas de changement DB
   ├─ UPDATE workspaces SET api_key_fingerprint = ? WHERE id = ?
   │  └─ fail → tenter Harpocrate.write(ancien_clair) (best-effort, log si KO)
   ├─ apikey_cache.invalidate(api_key_ref)
   └─ 200 {api_key (nouveau clair, one-shot)}
```

### 6.4 Boot greenfield

```
backend lifespan start
   │
   ├─ load Settings (plus de api_key_dek)
   ├─ migrations DB → applique 015 → schema à jour
   ├─ count(*) workspaces > 0 ?
   │  ├─ oui → count(*) harpocrate_vaults > 0 ?
   │  │   ├─ oui → ok, continue
   │  │   └─ non → RuntimeError "workspaces présents mais aucun coffre"
   │  └─ non → ok, continue
   └─ app ready
```

## 7. Tests

### 7.1 Tests modifiés

- `backend/tests/api/test_admin_workspaces.py` — adapter fixtures (retire
  `RAG_API_KEY_DEK`), body POST inclut `api_key_vault`.
- `backend/tests/api/test_mcp.py` — adapter fixtures, stub `SecretResolver`.
- `backend/tests/auth/test_workspace_auth.py` — refactor : plus de DEK, stub
  `SecretResolver` et `ApiKeyCache`.

### 7.2 Tests nouveaux

`backend/tests/services/test_workspace_create_harpocrate.py` (4 tests) :
- `test_create_workspace_writes_to_harpocrate_under_wsapi_path_returns_full_ref`
- `test_create_workspace_with_missing_vault_returns_vault_not_found`
- `test_create_workspace_rolls_back_harpocrate_on_db_insert_failure`
- `test_create_workspace_db_insert_failure_does_not_leave_secret_in_harpocrate`

`backend/tests/services/test_workspace_rotate_apikey.py` (4 tests) :
- `test_rotate_apikey_updates_harpocrate_value_and_fingerprint`
- `test_rotate_apikey_invalidates_cache`
- `test_rotate_apikey_returns_new_clear_value`
- `test_rotate_apikey_harpocrate_write_failed_rolls_back_db`

`backend/tests/auth/test_workspace_auth_harpocrate.py` (5 tests) :
- `test_require_apikey_cache_hit_does_not_call_harpocrate`
- `test_require_apikey_cache_miss_resolves_from_harpocrate_and_caches`
- `test_require_apikey_harpocrate_unreachable_returns_503`
- `test_require_apikey_wrong_key_returns_401`
- `test_require_apikey_unknown_workspace_returns_401`

`backend/tests/services/test_apikey_cache.py` (4 tests purs) :
- `test_cache_put_then_get_returns_value`
- `test_cache_no_ttl_value_persists`
- `test_cache_invalidate_evicts_entry`
- `test_cache_unknown_ref_returns_none`

`backend/tests/test_boot_no_default_vault.py` (1 test) :
- `test_boot_workspaces_table_non_empty_and_no_vaults_raises_runtime_error`

**Total nouveau** : 18 tests.

### 7.3 Stub `SecretResolver` étendu

Le `_ApiStubResolver` existant (`backend/tests/api/conftest.py`) doit accepter
les nouvelles refs `${vault://<v>:wsapi_<name>}` en plus des refs existantes.
Extension du set `known` dans la fixture.

### 7.4 Vérification "code mort"

À la fin du refactor :
```bash
grep -rn "api_key_dek\|API_KEY_DEK\|api_key_encrypted" backend/src/
```
Doit retourner uniquement la migration `010_workspace_apikey_encrypted.sql`
(historique, intouché par convention).

## 8. Plan de livraison

8 tâches TDD, à détailler dans un plan séparé :

- **T1** — Refactor `ApiKeyCache` (process-lifetime) + 4 tests purs.
- **T2** — Migration DB 015 + retrait `api_key_dek` de Settings + `.env.example`.
- **T3** — Schémas (`api_key_vault` dans `WorkspaceCreateRequest`) + 3 nouvelles
  erreurs typées.
- **T4** — Refactor `create_workspace` + 4 tests services.
- **T5** — Refactor `rotate_apikey` + 4 tests services.
- **T6** — Refactor `workspace_auth` + 5 tests auth.
- **T7** — Adapt routes admin + MCP (existants) + adapt tests.
- **T8** — Boot guard `RuntimeError` si workspaces non vides et 0 coffres +
  test + smoke manuel greenfield.

Estimation : **8 tâches, ~2 jours** avec subagent-driven discipliné.

## 9. Hors-scope explicite

1. **OIDC `client_secret_ref`** reste sur le pattern actuel (résolution via
   coffre par défaut). Pas touché.
2. **`indexer_configs.api_key_ref`** : aujourd'hui stocke juste le path
   logique (résolu via coffre par défaut). Pas aligné sur le nouveau
   formalisme strict. À laisser tel quel pour ce jalon.
3. **`rerank_configs.api_key_ref`** : idem.
4. **IHM pour changer le coffre d'un workspace existant** : non couvert. Si
   besoin de changer le coffre, c'est DELETE/CREATE workspace.
5. **Cache distribué multi-instance** : process-lifetime suffit pour
   mono-instance. À revoir si N instances backend un jour.
6. **Audit log des rotations** : pas dans ce jalon.
7. **Politique d'expiration des api_keys** : pas de TTL, éternel jusqu'à
   rotation manuelle.

## 10. Risques

| Risque | Mitigation |
|---|---|
| Harpocrate down → backend MCP cassé pour workspaces non encore en cache | 503 explicite + cache process-lifetime absorbe les pannes courtes. SPOF Harpocrate connu, accepté. |
| Rollback Harpocrate après échec INSERT DB échoue (secret orphelin) | Log structuré `harpocrate.orphan.secret` avec le path → opérateur peut nettoyer manuellement via IHM Harpocrate. Best-effort. |
| Path collision (`wsapi_<name>`) après suppression incomplète d'un workspace | Le write est idempotent (upsert). Si la row workspace n'a pas été DELETE → unique violation DB sur `name` avant write Harpocrate. Cas safe. |
| Cache stale après rotation manquant l'invalidate | Invalidate explicite dans le code + test dédié `test_rotate_apikey_invalidates_cache`. |
| `wsapi_<name>` collision entre workspaces de coffres différents | Pas de collision : un workspace = un coffre = un path. Chaque coffre Harpocrate a son propre namespace. |
| Backend redémarrage = perte du cache → première requête par workspace plus lente | Acceptable. Cold cache se reconstruit transparentement. Latence ajoutée 1 fois par workspace par cycle de vie process. |
