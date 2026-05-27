# M5d-backend — Exploitation SDK Harpocrate 0.6.0 (design)

**Date** : 2026-05-16
**Statut** : design (à reviewer)
**Portée** : backend uniquement. La consommation côté UI (autocomplete `api_key_ref`, sélecteur de type, etc.) est traitée dans un jalon ultérieur M5d-frontend.
**Précédent** : M5c-backend (`tag m5c-backend-done`) qui a migré la config Harpocrate vers la DB, et migration SDK 0.4.0 → 0.6.0 (commit `a9754be`).

## 1. Objectif

Exploiter trois familles de capacités introduites par le SDK Harpocrate 0.6.0 (`vendor/harpocrate-sdk/`) :

1. **Enrichissements API admin** : remplacer le probe heuristique de `test_connection` par `client.whoami()` (vraie validation d'auth, plus rapide, sans noise log), et exposer les métadonnées du wallet (`client.info()`) en complément.
2. **Catalogue de types** : exposer `client.types.list/get` aux admins via un endpoint dédié, pour préparer une UI de sélection de type lors de la création d'un secret/coffre.
3. **Listing des secrets d'un coffre** : exposer `client.secrets.list_secrets()` aux admins, sans les valeurs, pour préparer un autocomplete de `api_key_ref` côté UI Workspaces.

Hors scope (jalon futur, cf. §10) : auto-rotation (`using_secret`/`notify_auth_error`), création de placeholders + populate, frontend.

## 2. Décisions de conception (brainstorming)

| # | Question | Décision |
|---|---|---|
| Q1 | Périmètre des features SDK 0.6.0 à exploiter | Enrichissements (whoami + info) + catalogue de types + listing secrets. Auto-rotation et placeholders reportés. |
| Q2 | Faut-il un cache backend pour list_types ? | Non. Endpoint admin lazy, Harpocrate fait son throttling. Cache à ajouter seulement si la fréquence devient problématique. |
| Q3 | Comportement `test_connection` quand `probe_path is None` | Migrer vers `client.whoami()`. Sémantique franche : succès = auth OK, 401/403 = auth KO. Le 404-vaut-OK fragile disparaît. |
| Q4 | Comportement `test_connection` quand `probe_path` renseigné | Inchangé. C'est un vrai test bout-en-bout demandé par l'admin sur un secret précis. |
| Q5 | Enrichir `VaultSummary` avec wallet_name + permissions ? | Non. Coût SDK à chaque GET. Préférer endpoint dédié `/info` lazy. |

## 3. Architecture cible

### 3.1 Modules modifiés

- `backend/src/rag/secrets/vault.py` — `HarpocrateVaultClient` étendu : `whoami()`, `info()`, `list_types()`, `list_secrets()`.
- `backend/src/rag/schemas/harpocrate_vaults.py` — 4 nouveaux schemas Pydantic.
- `backend/src/rag/services/harpocrate_vaults.py` — 3 nouvelles méthodes service + refactor `test_connection`.
- `backend/src/rag/api/admin_harpocrate_vaults.py` — 3 nouveaux endpoints.

### 3.2 Modules NON modifiés

- `secrets/client_provider.py` (le provider ne change pas — il continue à fournir le `HarpocrateVaultClient`).
- `secrets/resolver.py` (résolution de refs `${vault://...}` inchangée).
- `secrets/bootstrap.py` (seed inchangé).
- Migration SQL 009 (pas de nouveau champ DB).
- Le wrapper interne `_LazyHarpocrateVaultClient` n'existe plus depuis M5c-T13.

## 4. Refactor `test_connection`

### 4.1 Comportement après

| Scénario | `probe_path` | Comportement | Résultat OK | Résultat KO |
|---|---|---|---|---|
| Auth-only | `None` | `client.whoami()` | `ok=True, detail="auth ok (whoami)"` | 401/403 ⇒ `ok=False, detail="auth refusée (401/403)"` |
| Test secret | non-None | `client.secrets.get(probe_path)` | `ok=True, detail="secret résolu"` | 401/403 ⇒ KO ; 404 ⇒ `ok=False, detail="probe_path introuvable"` ; autre ⇒ KO erreur SDK |

### 4.2 Différence vs M5c

- M5c : si `probe_path is None`, on tente `get_secret("__probe__")` et on classe le 404 comme "auth OK" (heuristique fragile).
- M5d : si `probe_path is None`, on fait `whoami()` qui répond directement sur l'auth. Plus de noise log côté Harpocrate (pas de secret lookup), plus rapide.

### 4.3 `VaultTestConnectionResult.probe_path_used`

Reste pour rétrocompat. Vaut `"whoami"` quand on a basculé sur whoami, sinon la valeur de probe_path.

## 5. Schemas Pydantic — ajouts à `schemas/harpocrate_vaults.py`

```python
class WalletInfoResponse(BaseModel):
    """Métadonnées du coffre exposées par GET /vaults/{id}/info.

    Combine client.whoami() (api_key context) + client.info() (wallet metadata).
    """
    wallet_id: UUID
    wallet_name: str | None          # depuis WalletInfo (None si non renseigné côté Harpocrate)
    api_key_id: str                  # depuis ApiKeyInfo
    permissions: list[str]           # depuis ApiKeyInfo ("read", "write", "add", "remove")
    api_key_expires_at: datetime | None


class SecretTypeSummary(BaseModel):
    """Résumé d'un type de secret du catalogue Harpocrate."""
    type_uuid: UUID
    type: str                        # ex "openai_api_key"
    sous_type: str | None
    label: str
    deprecated: bool


class SecretListItem(BaseModel):
    """Résumé d'un secret du wallet (sans valeur)."""
    id: UUID
    name: str
    description: str | None
    is_placeholder: bool
    tags: list[str]


class SecretListResponse(BaseModel):
    """Réponse paginée de GET /vaults/{id}/secrets."""
    secrets: list[SecretListItem]
    next_cursor: str | None
```

Note : ces schemas sont des **DTOs de relais** — leur job est d'adapter les modèles SDK (`ApiKeyInfo`, `WalletInfo`, `SecretType`, `SecretInfo`) en JSON stable pour notre API. Si le SDK change ses modèles internes, on absorbe le diff dans le mapping côté service, pas dans nos DTOs.

## 6. Wrapper SDK `HarpocrateVaultClient` étendu (`secrets/vault.py`)

```python
class HarpocrateVaultClient:
    def __init__(self, url: str, token: str) -> None: ...
    def get_secret(self, path: str) -> str: ...                                 # existe (M5c)

    # M5d
    def whoami(self) -> ApiKeyInfo: ...                                         # client.whoami()
    def info(self) -> WalletInfo: ...                                           # client.info()
    def list_types(self, q: str | None = None, include_deprecated: bool = False) -> list[SecretType]: ...
    def list_secrets(
        self,
        tag: str | None = None,
        name_contains: str | None = None,
        path: str | None = None,
        limit: int = 50,
    ) -> SecretListResponse: ...                                                # client.secrets.list_secrets()
```

Le wrapper continue à instancier le SDK paresseusement et conserve l'interface stable consommée par `SecretResolver` (`get_secret`).

## 7. Service `HarpocrateVaultsService` — 3 nouvelles méthodes

### 7.1 `get_wallet_info(conn, vault_id) -> WalletInfoResponse`

1. Lit le vault (raise `VaultNotFoundError` si inconnu).
2. Déchiffre l'api_key via `reveal_api_key`.
3. Instancie `HarpocrateVaultClient(url=vault.base_url, token=api_key)`.
4. Combine `client.whoami()` (api_key_id + permissions + expires_at) + `client.info()` (wallet_id + wallet_name).
5. Retourne `WalletInfoResponse`.

### 7.2 `list_types(conn, vault_id, *, q=None, include_deprecated=False) -> list[SecretTypeSummary]`

1. Lit le vault + reveal_api_key.
2. Instancie client. Appelle `client.types.list(q, include_deprecated)`.
3. Map chaque `SecretType` en `SecretTypeSummary`.

### 7.3 `list_wallet_secrets(conn, vault_id, *, path=None, name_contains=None, tag=None, limit=50) -> SecretListResponse`

1. Lit le vault + reveal_api_key.
2. Instancie client. Appelle `client.secrets.list_secrets(...)`.
3. Map chaque `SecretInfo` en `SecretListItem`. Propage `next_cursor`.

### 7.4 Refactor `test_connection` (méthode existante)

```python
async def test_connection(self, conn, vault_id) -> VaultTestConnectionResult:
    vault = await self.get_by_id(conn, vault_id)
    if vault is None:
        raise VaultNotFoundError(str(vault_id))
    api_key = await self.reveal_api_key(conn, vault_id)
    if api_key is None:
        raise VaultNotFoundError(str(vault_id))

    client = HarpocrateVaultClient(url=vault.base_url, token=api_key)

    # Cas auth-only : pas de probe_path → whoami()
    if vault.probe_path is None:
        try:
            client.whoami()
            return VaultTestConnectionResult(
                ok=True, detail="auth ok (whoami)", probe_path_used="whoami",
            )
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            log.info("vault.test_connection", vault_id=str(vault_id), ok=False, status_code=status_code, mode="whoami")
            if status_code in (401, 403):
                return VaultTestConnectionResult(ok=False, detail=f"auth refusée ({status_code})", probe_path_used="whoami")
            return VaultTestConnectionResult(ok=False, detail=f"erreur SDK : {type(exc).__name__}", probe_path_used="whoami")

    # Cas test bout-en-bout : probe_path renseigné → get_secret
    path = vault.probe_path
    try:
        client.get_secret(path)
        return VaultTestConnectionResult(ok=True, detail="secret résolu", probe_path_used=path)
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        log.info("vault.test_connection", vault_id=str(vault_id), ok=False, status_code=status_code, probe_path_used=path)
        if status_code in (401, 403):
            return VaultTestConnectionResult(ok=False, detail=f"auth refusée ({status_code})", probe_path_used=path)
        if status_code == 404:
            return VaultTestConnectionResult(ok=False, detail=f"probe_path '{path}' introuvable", probe_path_used=path)
        return VaultTestConnectionResult(ok=False, detail=f"erreur SDK : {type(exc).__name__}", probe_path_used=path)
```

## 8. Router — 3 nouveaux endpoints

| Méthode | Path | Query params | Réponse |
|---|---|---|---|
| `GET` | `/api/admin/harpocrate-vaults/{vault_id}/info` | — | `WalletInfoResponse` |
| `GET` | `/api/admin/harpocrate-vaults/{vault_id}/types` | `q?`, `include_deprecated?=false` | `list[SecretTypeSummary]` |
| `GET` | `/api/admin/harpocrate-vaults/{vault_id}/secrets` | `path?`, `name_contains?`, `tag?`, `limit?=50` | `SecretListResponse` |

Tous derrière `require_master_key_or_oidc_role("rag-admin")`. Tous lazy (appel SDK à chaque requête).

### 8.1 Codes d'erreur

| Code | Origine |
|---|---|
| `401` | Pas de master-key, pas de session OIDC |
| `403` | OIDC sans rôle `rag-admin` |
| `404` | `VaultNotFoundError` (id inconnu) |
| `502` | Erreur réseau ou statut HTTP non-recovrable côté SDK Harpocrate (timeout, 5xx) |
| `422` | Query param invalide (limit hors bornes…) |

### 8.2 Logs structurés (nouveaux events)

| Event | Niveau | Champs |
|---|---|---|
| `vault.info_fetched` | info | vault_id, wallet_id, actor |
| `vault.types_listed` | info | vault_id, count, actor |
| `vault.secrets_listed` | info | vault_id, count, path, actor |
| `vault.test_connection` (mode étendu) | info | vault_id, ok, status_code, mode (`whoami` ou `probe`), probe_path_used |

## 9. Tests d'intégration prévus

### 9.1 Tests service (mocks SDK)

- `test_test_connection_uses_whoami_when_no_probe_path`
- `test_test_connection_whoami_401_returns_ko`
- `test_test_connection_with_probe_path_unchanged_OK`
- `test_test_connection_with_probe_path_404_returns_ko`
- `test_get_wallet_info_combines_whoami_and_info`
- `test_get_wallet_info_raises_when_vault_absent`
- `test_list_types_relays_sdk`
- `test_list_types_with_q_filter`
- `test_list_types_include_deprecated`
- `test_list_wallet_secrets_returns_paginated`
- `test_list_wallet_secrets_with_path_filter`

### 9.2 Tests HTTP (router)

- `test_get_info_endpoint_returns_wallet_info`
- `test_get_info_endpoint_returns_404_when_vault_absent`
- `test_get_types_endpoint_returns_catalog`
- `test_get_secrets_endpoint_returns_list`
- `test_get_secrets_endpoint_respects_limit_param`
- `test_anonymous_returns_401_on_info` (un échantillon suffit)

### 9.3 Adaptations tests existants

- `test_test_connection_404_without_probe_path_is_ok` (M5c) → renommer `test_test_connection_without_probe_path_uses_whoami`. La sémantique a changé.

## 10. Hors scope M5d-backend (futurs jalons)

| Feature SDK | Statut | Jalon potentiel |
|---|---|---|
| Auto-rotation (`using_secret`, `notify_auth_error`) | Reporté | M5e (résilience indexer) |
| Création de placeholders + `populate` | Reporté | Jalon dédié si l'admin en a besoin pour secrets internes |
| Frontend Settings consommant `/types`, `/secrets`, `/info` | Reporté | M5d-frontend |
| Cache backend des types | Reporté | À ajouter si profil prouve un besoin |
| `client.secrets.create/put/patch/delete` via API admin | Hors scope | L'admin gère les secrets directement via UI Harpocrate, pas via notre backend |

## 11. Critères de complétion M5d-backend

- 4 méthodes ajoutées au wrapper `HarpocrateVaultClient` (`whoami`, `info`, `list_types`, `list_secrets`)
- 3 nouvelles méthodes ajoutées à `HarpocrateVaultsService` + refactor `test_connection`
- 3 nouveaux endpoints exposés et documentés OpenAPI
- 4 nouveaux schemas Pydantic
- ~15 tests d'intégration (service + router) verts sur LXC test
- Test existant `test_test_connection_404_without_probe_path_is_ok` adapté à la nouvelle sémantique whoami
- Ruff propre, smoke import OK
- Déployé sur LXC 303 via `./dev-deploy.sh`
- Tag `m5d-backend-done` poussé

## 12. Pièges identifiés à anticiper

1. **Mocks SDK** : les tests M5c mockaient `HarpocrateVaultClient` ; les tests M5d doivent étendre les mocks pour les nouvelles méthodes (`whoami`, `info`, `list_types`, `list_secrets`). Garder un mock factory commun.
2. **Mapping SDK → DTO** : `SecretType.sous_type` peut être `None` ou absent selon la version du serveur Harpocrate — défensif (`getattr(t, "sous_type", None)`).
3. **`SecretListResponse.next_cursor`** : pagination opaque, à propager tel quel. L'API ne tente PAS de remonter ou interpréter la valeur.
4. **`whoami` peut lever `httpx.HTTPStatusError` ou exception custom du SDK** — la classification du statut suit le pattern existant (`getattr(getattr(exc, "response", None), "status_code", None)`).
5. **`info()` du SDK appelle `/v1/wallets/{wallet_id}` côté Harpocrate** — peut renvoyer 403 si l'api_key n'a pas les droits read sur le wallet. Mapper en 502 côté backend avec message clair.
6. **`probe_path_used="whoami"`** est une sentinelle réservée. Si jamais quelqu'un nomme un secret `whoami`, c'est un faux conflict côté UI. Documentation explicite mais pas de validation backend (le slug est juste informatif).

## 13. Suite

1. User review de cette spec
2. Plan TDD dans `docs/superpowers/plans/2026-05-16-M5d-backend-harpocrate-features.md`
3. Exécution subagent-driven
4. Déploiement LXC 303 via `./dev-deploy.sh`
5. Tag `m5d-backend-done`
