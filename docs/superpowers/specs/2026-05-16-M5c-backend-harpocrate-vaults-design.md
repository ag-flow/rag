# M5c-backend — Coffres Harpocrate configurables côté DB (design)

**Date** : 2026-05-16
**Statut** : design (à reviewer)
**Portée** : backend uniquement. La page Settings UI est traitée dans un jalon ultérieur M5c-frontend.
**Référence** : `specs/11-harpocrate-indatabase.md` (spec d'origine héritée du projet `agflow.docker`).

## 1. Objectif

Migrer la configuration des coffres Harpocrate du fichier `.env` vers une table DB chiffrée (`harpocrate_vaults`), exposer une API admin REST permettant CRUD + rotation api_key + test de connexion, et faire évoluer le `SecretResolver` pour lire dynamiquement les coffres depuis la base au lieu d'un dictionnaire figé construit au boot.

Le jalon préserve la rétrocompatibilité : si la table est vide au démarrage et que des variables d'env `HARPOCRATE_API_TOKEN_<ID>` / `HARPOCRATE_API_URL_<ID>` sont définies, un seed automatique crée un coffre par paire (avec `name=<id en minuscule>`), de sorte que les refs déjà semées en DB de la forme `${vault://rag:...}` continuent de fonctionner sans migration data.

## 2. Décisions de conception (brainstorming)

| # | Question | Décision |
|---|---|---|
| Q1 | Découpage backend/frontend | Deux jalons séparés livrés et tagués indépendamment : M5c-backend puis M5c-frontend |
| Q2 | Source de configuration | DB-first ; fallback env vars uniquement si la table est vide ; env ignoré dès qu'un coffre est en DB |
| Q3 | Stratégie test_connection | Colonne `probe_path` nullable par coffre. Endpoint `POST .../test-connection` appelle `get_secret(probe_path)` si renseigné, sinon `get_secret("__probe__")` avec sémantique 401/403 = KO, 404 = OK |
| Q4 | Rétrocompat des refs `${vault://rag:...}` | Refs dynamiques via helper `build_ref(default_vault_name, path)`. Le seed automatique crée le premier coffre avec `name="rag"` pour préserver les refs existantes sans migration de données. `name` immuable après création |

## 3. Architecture cible

### 3.1 Modules créés

- `backend/migrations/004_harpocrate_vaults.sql` — schéma de la table
- `backend/src/rag/schemas/harpocrate_vaults.py` — DTOs Pydantic v2
- `backend/src/rag/services/harpocrate_vaults.py` — service CRUD + chiffrement
- `backend/src/rag/api/admin/harpocrate_vaults.py` — router FastAPI
- `backend/src/rag/secrets/refs.py` — helpers purs `parse_ref` / `build_ref` / `is_vault_ref`
- `backend/src/rag/secrets/client_provider.py` — `HarpocrateClientProvider` (cache et fournit les clients)
- `backend/src/rag/secrets/bootstrap.py` — `seed_vaults_from_env_if_empty`

### 3.2 Modules modifiés

- `backend/src/rag/config.py` — suppression du validator exigeant ≥ 1 paire Harpocrate ; ajout `harpocrate_dek: SecretStr | None`
- `backend/src/rag/main.py` — lifespan recâblé (service, provider, resolver, seed)
- `backend/src/rag/secrets/resolver.py` — passe d'un `dict[str, VaultClient]` à un `HarpocrateClientProvider` ; `resolve_ref` devient async
- `backend/src/rag/services/{workspaces,sources,jobs,mcp,oidc}.py` — `default_vault_name` reçu en argument explicite
- `backend/src/rag/indexer/real.py` — idem
- `backend/src/rag/sync/executor.py` — idem ; le worker tient une référence au `client_provider` et résout le default à chaque tick

## 4. Schéma SQL — migration `009_harpocrate_vaults.sql`

**Note de numérotation** : la plus haute migration existante au moment du chantier est `008_ollama_mxbai_embed_large.sql`. La migration M5c prend donc `009_*`.

```sql
CREATE TABLE harpocrate_vaults (
    id                uuid PRIMARY KEY,
    name              text NOT NULL UNIQUE,
    label             text NOT NULL,
    base_url          text NOT NULL,
    api_key_id        text NOT NULL,
    api_key_encrypted bytea NOT NULL,
    probe_path        text NULL,
    is_default        boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX harpocrate_vaults_one_default
    ON harpocrate_vaults (is_default)
    WHERE is_default;

CREATE INDEX harpocrate_vaults_name ON harpocrate_vaults (name);
```

**Pré-requis** : extension `pgcrypto` (activée en `001_init.sql`).

**Maintenance de `updated_at`** : par convention projet (cf. `services/workspaces.py:214, 260`), `updated_at = now()` est maintenu **côté service Python** dans chaque UPDATE. Pas de trigger SQL. Le service `HarpocrateVaultsService` doit explicitement inclure `, updated_at = now()` dans toutes ses méthodes `update`, `rotate_api_key`, `set_default`.

**Contraintes** :

- `name` : slug technique `^[a-z][a-z0-9_-]{2,63}$` (validé Pydantic)
- `base_url` : préfixé `http://` ou `https://`, sans slash final
- `probe_path` : si renseigné, `^[a-zA-Z0-9_/-]+$`
- `api_key_encrypted` : produit par `pgp_sym_encrypt(api_key::text, harpocrate_dek::text)` ; jamais d'INSERT/UPDATE en clair

## 5. Variable d'environnement nouvelle — `HARPOCRATE_DEK`

- Passphrase pgcrypto utilisée comme `SECRET_KEY` du `pgp_sym_encrypt`/`pgp_sym_decrypt`
- Validateur Pydantic : `len(raw) >= 32` (sinon `ValidationError` à l'init)
- Type : `SecretStr | None` (None autorisé si DB vide et aucun seed à faire)
- Vérification runtime : `HarpocrateClientProvider._load()` raise `HarpocrateDekMissingError` si la table contient ≥ 1 ligne mais `harpocrate_dek is None` → crash du lifespan (fail fast au boot)
- Documentation `.env.example` : doubler tout `$` en `$$` si le fichier est consommé via `docker-compose env_file` (piège #4)

## 6. Schemas Pydantic — `schemas/harpocrate_vaults.py`

- `VaultSummary` (réponse list/get) : `id`, `name`, `label`, `base_url` (str, pas HttpUrl), `api_key_id`, `probe_path`, `is_default`, timestamps. **Pas de champ api_key**.
- `VaultCreateRequest` : `name`, `label`, `base_url`, `api_key_id`, `api_key`, `probe_path?`, `is_default=False`. Validators `name`/`base_url`/`probe_path`.
- `VaultUpdateRequest` : PATCH partiel sur `label`, `base_url`, `probe_path`. **Pas de `name`** (immuable). **Pas de `is_default`** (passe par endpoint dédié). Configuré `model_config = ConfigDict(extra="forbid")` pour rejeter explicitement les champs interdits (`name`, `is_default`) en `422 Unprocessable Entity`.
- `VaultRotateApiKeyRequest` : `api_key_id`, `api_key`.
- `VaultTestConnectionResult` : `ok: bool`, `detail: str`, `probe_path_used: str`.
- `VaultRevealApiKeyResponse` : `id`, `api_key_id`, `api_key` (valeur claire). Retourné par endpoint séparé sous audit-log.

**Piège #5 (Pydantic v2 `HttpUrl` ajoute un slash)** : `base_url` est typé `str` partout, jamais `HttpUrl`.

## 7. Service — `services/harpocrate_vaults.py`

Classe `HarpocrateVaultsService` à instance unique (créée au lifespan, injectée via `Depends`). Cache mémoire du coffre `is_default` avec TTL 60 secondes, invalidé sur tout write.

### Méthodes

| Méthode | Signature | Comportement clé |
|---|---|---|
| `list_all` | `(conn) -> list[VaultSummary]` | SELECT all + tri sur `created_at` |
| `get_by_id` | `(conn, vault_id) -> VaultSummary \| None` | SELECT WHERE id |
| `get_by_name` | `(conn, name) -> VaultSummary \| None` | SELECT WHERE name |
| `get_default` | `(conn) -> VaultSummary \| None` | Cache 60s + SELECT WHERE is_default |
| `reveal_api_key` | `(conn, vault_id) -> str \| None` | `pgp_sym_decrypt(api_key_encrypted, dek)` |
| `create` | `(conn, req) -> VaultSummary` | UUID Python, INSERT avec `pgp_sym_encrypt(api_key, dek)`. Si `is_default=True` : UPDATE préalable `is_default=false WHERE is_default=true` dans la même transaction |
| `update` | `(conn, vault_id, req) -> VaultSummary \| None` | UPDATE partiel sur `label`/`base_url`/`probe_path` |
| `rotate_api_key` | `(conn, vault_id, req) -> VaultSummary \| None` | UPDATE `api_key_id` + `api_key_encrypted` |
| `set_default` | `(conn, vault_id) -> VaultSummary \| None` | Transaction : UPDATE `is_default=false WHERE is_default=true` puis UPDATE `is_default=true WHERE id=$1` |
| `delete` | `(conn, vault_id) -> bool` | DELETE WHERE id. Refus 409 si `is_default=true` ET autres coffres existent → contrôle dans le router avant le DELETE |
| `test_connection` | `(conn, vault_id) -> VaultTestConnectionResult` | Lit le coffre, déchiffre api_key, instancie `HarpocrateVaultClient`, appelle `get_secret(probe_path or "__probe__")`, classifie l'erreur |

### Logique `test_connection`

- `path = vault.probe_path or "__probe__"`
- Succès `get_secret(path)` → `ok=True, detail="secret résolu"`
- Erreur SDK avec status code :
  - 401/403 → `ok=False, detail="auth refusée (401/403)"`
  - 404 et `probe_path is None` → `ok=True, detail="auth ok (404 sur __probe__ — secret inexistant attendu)"`
  - 404 et `probe_path is not None` → `ok=False, detail=f"probe_path '{path}' introuvable"`
  - Autre / réseau → `ok=False, detail=<msg court non-leaky>`

### Exceptions

```python
class HarpocrateVaultsError(Exception): ...
class HarpocrateDekMissingError(HarpocrateVaultsError): ...
class VaultNameAlreadyExistsError(HarpocrateVaultsError): ...
class VaultNotFoundError(HarpocrateVaultsError): ...   # existait déjà dans secrets/resolver.py — déplacé/factorisé
```

### Invalidation du `client_provider`

Le service expose `bind_client_provider(provider)` pour injection post-construction (évite le cycle d'import). Chaque méthode write appelle `self._client_provider.invalidate()` en fin de méthode si lié.

## 8. Router — `api/admin/harpocrate_vaults.py`

Préfixe `/api/admin/harpocrate-vaults`. Garde commune `Depends(require_master_key_or_oidc_role("rag-admin"))`.

| Méthode | Path | Status | Réponse | Description |
|---|---|---|---|---|
| `GET` | `/` | 200 | `list[VaultSummary]` | Liste |
| `POST` | `/` | 201 | `VaultSummary` | Création |
| `GET` | `/{vault_id}` | 200 | `VaultSummary` | Détail |
| `PATCH` | `/{vault_id}` | 200 | `VaultSummary` | MAJ partielle (`label`, `base_url`, `probe_path`) |
| `DELETE` | `/{vault_id}` | 204 | _vide_ | Refus 409 si `is_default=True` avec d'autres coffres |
| `POST` | `/{vault_id}/rotate-api-key` | 200 | `VaultSummary` | Remplace api_key + api_key_id |
| `POST` | `/{vault_id}/set-default` | 200 | `VaultSummary` | Bascule le default (atomique) |
| `POST` | `/{vault_id}/test-connection` | 200 | `VaultTestConnectionResult` | Probe SDK |
| `GET` | `/{vault_id}/api-key` | 200 | `VaultRevealApiKeyResponse` | **Audit-loggué** — déchiffre la valeur claire |

### Codes d'erreur

| Code | Origine |
|---|---|
| `400` | ValidationError Pydantic (slug invalide, base_url malformée…) |
| `401` | Pas de master-key, pas de session OIDC valide |
| `403` | OIDC sans rôle `rag-admin` |
| `404` | `VaultNotFoundError` |
| `409` | `VaultNameAlreadyExistsError` ou DELETE d'un default tant que d'autres coffres existent |
| `422` | Body JSON malformé |
| `502` | `test-connection` : erreur réseau inattendue côté SDK |

### Audit & logs

- Tous les endpoints write loggent avec `actor` (`"master-key"` ou `f"oidc:{sub}"`) via la dependency `get_current_actor()` héritée de M5a.
- `GET /{vault_id}/api-key` log `log.warning("vault.reveal", vault_id=..., actor=...)` — trace Loki dédiée car seul endpoint qui sort un secret en clair.
- `test-connection` log `log.info("vault.test_connection", vault_id=..., ok=..., status_code=...)`. Jamais la valeur d'api_key, même partielle.

## 9. Helpers refs — `secrets/refs.py`

Module pur, pas d'I/O.

- `parse_ref(ref: str) -> tuple[str, str]` — regex `^\$\{vault://([^:}]+):([^}]+)\}$`, raise `ValueError` si format invalide.
- `build_ref(vault_name: str, path: str) -> str` — construit la ref, ne valide pas l'existence du coffre.
- `is_vault_ref(value: str) -> bool` — match sans extraire.

## 10. `HarpocrateClientProvider` — `secrets/client_provider.py`

Cache et fournit les `HarpocrateVaultClient` par nom. Source DB-first avec fallback env. TTL mémoire 60 secondes + invalidation manuelle.

### API publique

```python
class HarpocrateClientProvider:
    def __init__(self, settings, vaults_service, db_pool): ...
    async def get_client(self, vault_name: str) -> VaultClient: ...   # raise VaultNotFoundError
    async def get_default_vault_name(self) -> str | None: ...
    def invalidate(self) -> None: ...
```

### Logique `_load()`

1. Ouvre une connexion via `db_pool`.
2. `vaults = await vaults_service.list_all(conn)`.
3. Si `vaults` non vide :
   - Pour chaque coffre : `api_key = await vaults_service.reveal_api_key(conn, v.id)` puis `clients[v.name] = HarpocrateVaultClient(url=v.base_url, token=api_key)`.
   - `default_name = next((v.name for v in vaults if v.is_default), None)`. Cas edge : si la table contient des coffres mais qu'aucun n'est `is_default=True` (état théoriquement atteignable seulement par DELETE du default puis pas de set_default ultérieur), `default_name` reste `None` et toute opération nécessitant l'écriture d'un secret retourne 503 jusqu'à ce que l'admin promeuve un coffre via `POST .../set-default`. Un event `vault.default_missing` (warning) est loggué une fois par `_load()`.
4. Sinon, si `settings.harpocrate_api_keys` non vide :
   - Pour chaque identifier : créer le client depuis env.
   - `default_name = min(identifiers)` (premier alphabétique).
5. Sinon : `clients = {}`, `default_name = None`. Toute résolution échouera.

`asyncio.Lock` interne pour sérialiser les `_load()` concurrents post-invalidation.

## 11. `SecretResolver` — refactor `secrets/resolver.py`

### Avant (M4)

```python
class SecretResolver:
    def __init__(self, harpocrate_clients: dict[str, VaultClient], *, cache_ttl: int = 300): ...
    def resolve_ref(self, ref: str) -> str: ...
```

### Après (M5c)

```python
class SecretResolver:
    def __init__(self, client_provider: HarpocrateClientProvider, *, cache_ttl: int = 300): ...
    async def resolve_ref(self, ref: str) -> str: ...
    async def resolve_with_retry(self, ref: str) -> str: ...
```

- `resolve_ref` devient async. Tous les appelants doivent ajouter `await`.
- Le cache TTL par ref reste inchangé.
- `resolve_with_retry` : sur 401, appelle `client_provider.invalidate()` puis retry une fois (rotation de clé en cours).

## 12. Refactor des sites qui construisent des refs

Les 7 sites listés ci-dessous reçoivent `default_vault_name: str` (ou `str | None` pour les chemins optionnels) en argument explicite ; le router le résout via `client_provider.get_default_vault_name()` avant d'appeler le service.

| Fichier | Forme actuelle | Remplacement |
|---|---|---|
| `services/workspaces.py:41` | `_to_vault_ref(logical_key, vault_id="rag")` | `_to_vault_ref(logical_key, vault_name)` utilisant `build_ref` |
| `services/sources.py:29` | `f"${{vault://rag:{path}}}"` inline | `build_ref(default_vault_name, path)` |
| `services/jobs.py:94` | idem inline | idem |
| `services/mcp.py:130` | idem inline | idem |
| `indexer/real.py:24` | idem inline | idem |
| `sync/executor.py:114` | idem inline | idem (worker tient `client_provider`, résout à chaque tick) |
| `services/oidc.py:329` | `f"${{vault://rag:{config.client_secret_ref}}}"` | `build_ref(default_vault_name, config.client_secret_ref)` |

### Comportement si `default_vault_name is None`

Le router gate : si l'opération nécessite l'écriture d'un secret et `default_vault_name is None` → `HTTPException(503, detail="aucun coffre Harpocrate configuré")`.

## 13. Bootstrap lifespan — `secrets/bootstrap.py`

Fonction `seed_vaults_from_env_if_empty(settings, pool, vaults_service)` appelée au lifespan après les migrations DB.

### Comportement

- Si la table contient déjà ≥ 1 coffre → skip (log info `vault.seed.skipped reason=table non vide`).
- Si `settings.harpocrate_api_keys` est vide → skip (log info `vault.seed.skipped reason=env vide`).
- Si `settings.harpocrate_dek is None` → log error `vault.seed.aborted` et skip. L'app démarre mais aucune résolution de ref ne fonctionnera ; l'admin doit corriger.
- Sinon : pour chaque identifier env (trié alphabétiquement), créer un coffre avec :
  - `name = identifier.lower()`
  - `label = f"Coffre {identifier} (seed env)"`
  - `base_url = str(cfg.url).rstrip("/")`
  - `api_key_id = f"env:{identifier}"`
  - `api_key = cfg.token.get_secret_value()`
  - `probe_path = None`
  - `is_default = (identifier == identifiers[0])`

Le seed est idempotent : un deuxième boot ne re-seed pas (skip car table non vide).

## 14. Câblage du lifespan — `main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db_pool = await create_pool(settings.database_url.get_secret_value())
    await run_migrations(db_pool)

    vaults_service = HarpocrateVaultsService(settings)
    client_provider = HarpocrateClientProvider(settings, vaults_service, db_pool)
    vaults_service.bind_client_provider(client_provider)

    await seed_vaults_from_env_if_empty(
        settings=settings, pool=db_pool, vaults_service=vaults_service,
    )

    resolver = SecretResolver(client_provider, cache_ttl=settings.secret_cache_ttl)

    app.state.db_pool = db_pool
    app.state.vaults_service = vaults_service
    app.state.client_provider = client_provider
    app.state.resolver = resolver

    sync_executor = SyncExecutor(client_provider=client_provider, ...)
    app.state.sync_executor = sync_executor
    sync_task = asyncio.create_task(sync_executor.run())

    try:
        yield
    finally:
        sync_task.cancel()
        await db_pool.close()
```

## 15. Matrice de scénarios

| Scénario | Table DB | Env Harpocrate | DEK | Résultat boot | Comportement runtime |
|---|---|---|---|---|---|
| Migration M5b → M5c avec env présent | vide | présent | présent | Seed crée 1 coffre `name="rag"` | Refs existantes résolues OK |
| Greenfield, admin va tout faire via UI | vide | absent | présent | OK, table vide | Opérations write avec secret → 503 tant qu'un coffre n'est pas créé |
| LXC 303 avec workspaces, DEK oublié | vide | présent | **absent** | Seed abort (log error) | Toute résolution échoue ; admin doit ajouter DEK et relancer |
| Admin a déjà créé des coffres | non vide | (ignoré) | présent | OK | DB seule |
| DEK manquant alors que table non vide | non vide | (peu importe) | absent | **Crash lifespan** (`HarpocrateDekMissingError`) | n/a |
| DEK < 32 chars | (peu importe) | (peu importe) | présent mais trop court | **Crash init Settings** (`ValidationError`) | n/a |

## 16. Audit et logs structurés

Liste exhaustive des événements structlog ajoutés :

| Event | Niveau | Champs |
|---|---|---|
| `vault.created` | info | vault_id, name, is_default, actor |
| `vault.updated` | info | vault_id, fields_changed, actor |
| `vault.deleted` | info | vault_id, name, actor |
| `vault.api_key_rotated` | info | vault_id, api_key_id_old, api_key_id_new, actor |
| `vault.default_changed` | info | vault_id_old, vault_id_new, actor |
| `vault.test_connection` | info | vault_id, ok, status_code, probe_path_used |
| `vault.reveal` | warning | vault_id, actor |
| `vault.seed.created` | info | name, is_default |
| `vault.seed.skipped` | info | reason |
| `vault.seed.aborted` | error | reason |
| `vault.default_missing` | warning | clients_count |

Aucun event ne logue jamais la valeur d'api_key, même partielle.

## 17. Tests prévus

### Unitaires

- `tests/unit/test_refs.py` : `parse_ref` valide/invalide, `build_ref` roundtrip, `is_vault_ref`
- `tests/unit/test_client_provider.py` :
  - charge depuis la DB si table non vide
  - fallback env si table vide
  - `default_vault_name` depuis la DB (is_default)
  - `default_vault_name` depuis env (premier alphabétique)
  - `invalidate()` force rechargement
  - lock sérialise les chargements concurrents
- `tests/unit/test_resolver.py` (adapté) : résolution async, retry-on-401 invalide le provider

### Intégration

- `tests/integration/test_admin_harpocrate_vaults.py` :
  - `test_create_returns_201_without_api_key_in_response` (assertion `'"api_key":' not in r.text`, piège #3)
  - `test_create_with_is_default_swaps_previous_default`
  - `test_create_duplicate_name_returns_409`
  - `test_create_invalid_slug_returns_400`
  - `test_list_returns_summaries_without_api_key`
  - `test_get_by_id_returns_summary`
  - `test_get_nonexistent_returns_404`
  - `test_patch_updates_label_base_url_probe_path`
  - `test_patch_name_field_rejected_422`
  - `test_patch_is_default_field_rejected_422`
  - `test_delete_default_with_others_returns_409`
  - `test_delete_default_alone_returns_204`
  - `test_rotate_api_key_changes_encrypted_value`
  - `test_set_default_swaps_atomically`
  - `test_test_connection_probe_path_configured_404_returns_ok_false`
  - `test_test_connection_probe_path_fallback_404_returns_ok_true`
  - `test_test_connection_401_returns_ok_false`
  - `test_reveal_api_key_logs_audit_event`
  - `test_admin_oidc_without_rag_admin_role_returns_403`
  - `test_admin_anonymous_returns_401`
- `tests/integration/test_seed_bootstrap.py` :
  - `test_seed_creates_vault_named_rag_when_env_present_and_db_empty`
  - `test_seed_skipped_when_db_non_empty`
  - `test_seed_skipped_when_env_empty`
  - `test_seed_aborted_when_dek_missing`
- `tests/integration/test_lifespan_with_empty_env_and_empty_db.py` : boot doit réussir, requêtes write nécessitant un secret renvoient 503

### Adaptations des tests existants (~25 tests)

Ajouter une fixture `default_vault_name` et passer l'argument supplémentaire aux fonctions de service. Mock du `HarpocrateClientProvider` au lieu du `dict[str, VaultClient]`.

## 18. Pièges à anticiper (hérités de `specs/11-harpocrate-indatabase.md`)

1. **NOT NULL `id`** : asyncpg n'auto-génère pas les UUID. Générer `uuid4()` côté Python avant l'INSERT.
2. **`monkeypatch.setattr` sur `get_settings`** : ne fonctionne pas si la fonction est importée au top du module testé. Utiliser `monkeypatch.setenv(...)` puis recharger.
3. **Assertion test "api_key" trop large** : `assert "api_key" not in r.text` faux-positiverait sur `api_key_id`. Utiliser `assert '"api_key":' not in r.text` avec le deux-points pour ne matcher que le champ exact.
4. **Docker Compose interpole `$`** : `HARPOCRATE_DEK=foo$bar` consommé via `env_file` devient `HARPOCRATE_DEK=foobar`. Doubler : `HARPOCRATE_DEK=foo$$bar`.
5. **`HttpUrl` Pydantic v2 ajoute un slash final** : `base_url` typé `str` partout, et `.rstrip("/")` dans les validators.
6. **SDK Harpocrate path-style buggy sur GET/UPDATE/DELETE imbriqués** : limitation connue du SDK, documentée. Pas de mitigation côté backend ; pertinence pour `probe_path` (éviter les `/` profonds si possible).

## 19. Périmètre exclu (différé à M5c-frontend)

- Page Settings React + onglets
- Composant `HarpocrateVaultsTab` (liste + formulaires create/edit/rotate)
- Modale "tester la connexion"
- Bouton "révéler la clé" avec confirmation
- Indicateur visuel default

Toute l'API est néanmoins testable via les tests d'intégration backend et via Swagger UI à `/docs`.

## 20. Critères de complétion M5c-backend

- Migration `004_harpocrate_vaults.sql` appliquée sur LXC 303
- 9 endpoints exposés à `/api/admin/harpocrate-vaults` et documentés OpenAPI
- Lifespan seed automatique opérationnel (vérifié : workspaces existants continuent de résoudre après redéploiement)
- Tous les tests unitaires + intégration passent (`uv run pytest -v`)
- `ruff check` et `ruff format` clean
- Loki : événements `vault.*` visibles dans Grafana
- Smoke manuel : créer, lister, get, update, rotate, set_default, test_connection, reveal_api_key, delete via `curl` avec master-key
- Tag `m5c-backend-done` posé sur le commit final

## 21. Suite

1. User review de cette spec
2. Plan TDD dans `docs/superpowers/plans/2026-05-16-M5c-backend-harpocrate-vaults.md`
3. Exécution subagent-driven (règle `subagent-driven-default`)
4. Déploiement LXC 303 via `./dev-deploy.sh`
5. Tag `m5c-backend-done`
6. Passage à M5c-frontend (avec mockups préalables, règle `frontend-mockups-before-dev`)
