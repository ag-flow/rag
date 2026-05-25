# M4b — API Push Synchrone : Spec de design

**Date** : 2026-05-15
**Branche** : `dev`
**Pré-requis** : M2 (`workspaces`, `indexer_configs`, `indexed_documents`, `apikey` bcrypt) + M4a (`RealIndexer`, `IndexerProtocol`, providers).

## 1. Objectif

Exposer l'endpoint `POST /workspaces/{name}/index` décrit dans
`specs/03-api-workspace.md` : un agent ag.flow pousse un document généré
(markdown, analyse, transcription) et obtient un `200 OK` une fois le
document indexé dans pgvector — sans dépendre d'un commit git.

Le moteur d'indexation (`RealIndexer`) existe déjà depuis M4a. M4b
ajoute : l'authentification par api_key workspace (avec cache LRU), le
router et le service de pré-déduplication.

## 2. Architecture

```
Agent ag.flow ──Bearer WS_API_KEY──► POST /workspaces/{name}/index
                                      │  body: { path, content }
                                      ▼
                require_workspace_apikey (dependency)
                  1. Lookup workspaces.name
                  2. Cache LRU hit ? compare_digest
                  3. Cache miss ? bcrypt verify + cache
                  → AuthContext(workspace_id, indexer_used)
                                      ▼
                services.push.push_document
                  1. normalize_path(payload.path)
                  2. content_hash = sha256(content)
                  3. SELECT content_hash FROM indexed_documents
                  4a. hash identique → 200 {status: skipped}
                  4b. hash diff → RealIndexer.index_file(...)
                                 → 200 {status: indexed, chunks, hash}
                  5. log structlog `push.indexed | push.skipped`
```

## 3. Décisions de design

| Sujet | Choix | Pourquoi |
|---|---|---|
| **Auth perf** | Cache LRU RAM, TTL 5 min, taille 256 | bcrypt rounds=12 = ~100 ms par requête. Sur le hot path d'un push, c'est inacceptable pour un agent qui pousse en série. Cache invalidé sur `rotate-apikey`. |
| **Observabilité** | Log structlog uniquement (Loki) | Pas de pollution de `index_jobs` (qui suppose `source_id NOT NULL` lié à une source git). Loki LXC 116 suffit pour l'historique. |
| **Limite content** | 5 MB UTF-8 | Couvre rapports, transcriptions. Au-delà, latence > 25 s incompatible avec HTTP synchrone. |
| **Validation path** | Strict POSIX relative | Cohérent avec les paths fournis par `git ls-files` côté sync worker. Rejette absolus, `..`, NUL, > 1024 chars. |
| **Discriminated union** | `PushIndexedResponse \| PushSkippedResponse` via `Field(discriminator="status")` | Sérialisation FastAPI propre des deux cas de succès, sans `JSONResponse` manuel. |
| **Race push / sync** | Last-writer-wins, pas de lock | `upsert_chunks` (M4a) fait DELETE+INSERT en transaction par `(workspace_id, path)`. Pas de corruption, juste un winner-takes-all. Conforme à la spec ("path est la clé d'upsert"). |
| **Pas de DELETE push** | Hors scope MVP | La spec 03 ne le mentionne pas. YAGNI. |
| **Pas de rate-limiting** | Hors scope M4b | Si un provider rate-limite, on remonte 502. Le rate-limiting RAG → M5+. |

## 4. Composants

### 4.1 Nouveaux modules

| Fichier | Rôle | LOC cible |
|---|---|---|
| `backend/src/rag/auth/workspace_auth.py` | `ApiKeyCache` (LRU+TTL), `require_workspace_apikey` dependency, `AuthContext` dataclass | ~120 |
| `backend/src/rag/api/workspace.py` | Router `build_workspace_router()` : 1 endpoint POST | ~50 |
| `backend/src/rag/services/push.py` | `normalize_path`, `push_document` (pré-dedup + appel RealIndexer) | ~100 |
| `backend/src/rag/schemas/workspace.py` | `PushRequest`, `PushIndexedResponse`, `PushSkippedResponse`, `PushResponse` (Annotated discriminated union) | ~50 |

### 4.2 Modifications de modules existants

- `backend/src/rag/api/errors.py` :
  - ajouter `InvalidPathError(RagApiError)` (422)
  - ajouter `EmbeddingProviderUnreachableHttpError(RagApiError)` (502)
  - register handler qui remappe `EmbeddingProviderError` (et ses sous-classes M4a) en 502
  - register handler qui remappe `ValueError("content_too_large")` Pydantic en 413

- `backend/src/rag/services/workspaces.py::rotate_apikey` :
  - paramètre additionnel `apikey_cache: ApiKeyCache | None = None`
  - sur succès UPDATE : `apikey_cache.invalidate(name)` si fourni

- `backend/src/rag/api/admin.py::rotate_apikey_endpoint` :
  - passer `request.app.state.apikey_cache` à `rotate_apikey()`

- `backend/src/rag/main.py` lifespan :
  - instancier `ApiKeyCache(max_size=256, ttl_seconds=300)` → `app.state.apikey_cache`
  - `app.include_router(build_workspace_router())`

## 5. ApiKeyCache — détail

### Interface

```python
class _CacheEntry:
    workspace_id: UUID
    indexer_used: str          # "<provider>/<model>"
    inserted_at: float         # time.monotonic()

class ApiKeyCache:
    def __init__(self, *, max_size: int = 256, ttl_seconds: int = 300) -> None
    def get(self, workspace_name: str, api_key: str) -> _CacheEntry | None
    def put(self, workspace_name: str, api_key: str, entry: _CacheEntry) -> None
    def invalidate(self, workspace_name: str) -> None
```

### Implémentation

- `OrderedDict[tuple[str, str], _CacheEntry]` interne.
- `get` :
  1. lookup clé `(name, api_key)`.
  2. si absent → `None`.
  3. si TTL expiré → `del` + `None`.
  4. sinon → `move_to_end()` + retour.
- `put` :
  1. insertion / mise à jour.
  2. si `len > max_size` → `popitem(last=False)` (évincte la plus ancienne).
- `invalidate(name)` :
  - itère et supprime toutes les entrées dont la clé commence par `name`.

### Garanties

- **Single-thread asyncio** : pas de lock nécessaire.
- **Aucune key plaintext loggée** : seuls `workspace_name`, `workspace_id`, `path` apparaissent dans les logs structlog.
- **Multi-instance scaling** : non géré en M4b — chaque instance a son propre cache. Documenté comme limite connue ; à corriger via Redis pub/sub en M5+ si on scale horizontalement.

## 6. Dependency `require_workspace_apikey`

```python
@dataclass
class AuthContext:
    workspace_id: UUID
    indexer_used: str

async def require_workspace_apikey(
    name: str,                  # path param
    request: Request,
) -> AuthContext:
    api_key = _extract_bearer(request)        # 401 si absent / scheme

    cache = request.app.state.apikey_cache
    pool  = request.app.state.pools.config_pool

    entry = cache.get(name, api_key)
    if entry is not None:
        return AuthContext(entry.workspace_id, entry.indexer_used)

    row = await pool.fetchrow(
        """SELECT w.id, w.api_key_hash,
                  ic.provider || '/' || ic.model AS indexer_used
           FROM workspaces w
           JOIN indexer_configs ic ON ic.workspace_id = w.id
           WHERE w.name = $1""",
        name,
    )
    if row is None:
        raise WorkspaceNotFoundError(name)            # 404

    if not verify_api_key(api_key, row["api_key_hash"]):
        raise HTTPException(401, "invalid_workspace_apikey")

    entry = _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )
    cache.put(name, api_key, entry)
    return AuthContext(row["id"], row["indexer_used"])
```

## 7. Service `push_document`

```python
async def push_document(
    *,
    payload: PushRequest,
    workspace_id: UUID,
    indexer_used: str,
    config_pool: asyncpg.Pool,
    indexer: IndexerProtocol,
) -> PushResponse:
    norm_path = normalize_path(payload.path)
    content_hash = "sha256:" + sha256(payload.content.encode("utf-8")).hexdigest()

    existing = await config_pool.fetchval(
        """SELECT content_hash FROM indexed_documents
           WHERE workspace_id = $1 AND path = $2""",
        workspace_id, norm_path,
    )
    if existing == content_hash:
        log.info("push.skipped", workspace_id=str(workspace_id),
                 path=norm_path, reason="content_unchanged")
        return PushSkippedResponse(path=norm_path)

    chunks = await indexer.index_file(
        workspace_id=workspace_id,
        path=norm_path,
        content=payload.content,
        content_hash=content_hash,
        indexer_used=indexer_used,
    )
    log.info("push.indexed", workspace_id=str(workspace_id),
             path=norm_path, chunks=chunks, hash=content_hash)
    return PushIndexedResponse(path=norm_path, chunks=chunks, hash=content_hash)
```

### Normalisation path

```python
_PATH_MAX_LEN = 1024
_BAD_SEGMENT  = re.compile(r"(^|/)\.\.(/|$)")

def normalize_path(raw: str) -> str:
    if "\x00" in raw:
        raise InvalidPathError("path_contains_nul")
    p = raw.replace("\\", "/")
    if p.startswith("/"):
        raise InvalidPathError("path_must_be_relative")
    if _BAD_SEGMENT.search(p):
        raise InvalidPathError("path_traversal_forbidden")
    if not p or len(p) > _PATH_MAX_LEN:
        raise InvalidPathError("path_invalid_length")
    return p
```

## 8. Schemas

```python
_CONTENT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB UTF-8

class PushRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=1024)
    content: str = Field(..., min_length=1)

    @field_validator("content")
    @classmethod
    def _content_size(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _CONTENT_MAX_BYTES:
            raise ValueError("content_too_large")
        return v

class PushIndexedResponse(BaseModel):
    path: str
    status: Literal["indexed"] = "indexed"
    chunks: int
    hash: str

class PushSkippedResponse(BaseModel):
    path: str
    status: Literal["skipped"] = "skipped"
    reason: Literal["content_unchanged"] = "content_unchanged"

PushResponse = Annotated[
    PushIndexedResponse | PushSkippedResponse,
    Field(discriminator="status"),
]
```

## 9. Matrice d'erreurs

| Code | Détail | Source | Quand |
|---|---|---|---|
| **200** | `{status: indexed, chunks: N, hash}` | router | succès |
| **200** | `{status: skipped, reason: content_unchanged}` | service | hash identique |
| **401** | `missing_bearer_token` | dep | pas d'header |
| **401** | `invalid_auth_scheme` | dep | scheme ≠ Bearer |
| **401** | `invalid_workspace_apikey` | dep | bcrypt verify échoue |
| **404** | `workspace_not_found` | dep | workspace absent ou indexer_config absent |
| **413** | `content_too_large` | handler | body > 5 MB UTF-8 |
| **422** | `invalid_path` + reason | service | path malformé |
| **422** | _(Pydantic standard)_ | DTO | body invalide |
| **502** | `embedding_provider_error` | handler | provider HS/auth/rate-limited |
| **500** | _(handler générique)_ | handler | bug interne (pas d'info fuitée) |

## 10. Tests

### Unit (sans DB, sans réseau)

- `tests/unit/auth/test_workspace_auth_cache.py` — couvre `ApiKeyCache` :
  miss, hit, TTL expired, LRU eviction, `invalidate(name)`.
- `tests/unit/services/test_push_path_normalize.py` — happy path, traversal,
  leading slash, NUL, vide, > 1024, edge case `foo/..bar` (non rejeté).
- `tests/unit/schemas/test_workspace_dto.py` — `PushRequest` accept/reject,
  borne content 5 MB ± 1, discriminated union sérialisation.

### Integration (DB jetable LXC 303 + fake indexer)

- `tests/integration/api/test_push_auth.py` — 404 workspace inconnu, 200 OK
  avec fake indexer, 401 api_key d'un autre workspace, vérification absence
  de re-bcrypt sur 2e requête (cache), invalidation cache sur rotate-apikey.
- `tests/integration/api/test_push_dedup.py` — push x2 même contenu → 2e
  skipped, push même path contenu différent → re-indexe, race concurrente
  same path → les deux passent (winner-takes-all).
- `tests/integration/api/test_push_errors.py` — body manquant 422, content
  5 MB+1 413, path `"../"` 422, sans Authorization 401, scheme non-bearer 401.

### Smoke opt-in (`@pytest.mark.smoke`)

- `tests/smoke/test_push_e2e.py` — workspace Ollama (URL homelab via
  `OLLAMA_TEST_URL`), push 1 doc, vérifie embeddings + indexed_documents
  populés avec dimension cohérente. Skippé sans `OLLAMA_TEST_URL`.

### Fixtures réutilisables

- `make_workspace(name, provider, model)` (M2) : retourne api_key clair +
  workspace_id.
- `fake_indexer` (M3) : in-memory IndexerProtocol comptant les appels.
- **Nouvelle** : `apikey_cache` (max_size=8, ttl=60) attaché à
  `app.state.apikey_cache`.

### Couverture cible

| Module | Cible |
|---|---|
| `auth/workspace_auth.py` | 100% |
| `services/push.py` | ≥ 95% |
| `api/workspace.py` | 100% (couvert via integration) |
| `schemas/workspace.py` | 100% |
| Couverture globale projet | ≥ 95% (maintenir le niveau M4a) |

## 11. Wiring `main.py`

Ajout dans le `lifespan` :

```python
from rag.auth.workspace_auth import ApiKeyCache
app.state.apikey_cache = ApiKeyCache(max_size=256, ttl_seconds=300)
```

Après le `include_router` admin existant :

```python
from rag.api.workspace import build_workspace_router
app.include_router(build_workspace_router())
```

## 12. Hors scope

- DELETE par push (retirer un doc précédemment poussé).
- Rate-limiting applicatif côté RAG.
- Batch push (`POST /workspaces/{name}/index/batch`).
- Granularité scopes api_key (read-only, write-only).
- Cache distribué multi-instance (Redis pub/sub).
- Trace push dans `index_jobs` / table dédiée.

Ces sujets sont reportés à M5+ et nécessitent une nouvelle spec.

## 13. Risques connus

| Risque | Mitigation |
|---|---|
| Timeout HTTP Caddy/Cloudflare > 25 s pour gros content (5 MB) | Documenter `Caddyfile` : `request_body { max_size 6MB }` et `timeouts { read_body 60s }`. Ajustement infra hors scope code mais à mentionner dans la PR. |
| `rotate-apikey` cross-instance | Cache local seulement → à corriger en M5+ (Redis pub/sub) si scaling. Documenté. |
| Race push vs sync worker même path | Last-writer-wins, conforme à la spec. Logs structlog côté push et côté worker permettent de tracer. |
| Cache poisoning via tentatives de mauvaises clés | Le cache ne contient que des succès bcrypt → un attaquant doit déjà connaître une clé valide pour polluer. Pas de risque. |
