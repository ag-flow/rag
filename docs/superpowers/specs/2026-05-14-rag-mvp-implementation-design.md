# Design d'implémentation — ag-flow.rag MVP

**Date** : 2026-05-14
**Auteur** : brainstorming Claude + black beard
**Scope** : implémentation des specs 00 à 10 + vault.md / internal_resolution-formalism.md
**Statut** : design validé, prêt pour découpage en plans d'implémentation

---

## Décisions de cadrage

| Décision | Choix retenu | Justification |
|---|---|---|
| Découpage | Jalons backend-first, 5 jalons backend + 1 jalon IHM + 1 jalon Alloy | Chaque jalon = verticale testable de bout en bout sur LXC 303 |
| Auth OIDC + IHM | Repoussées en jalon final (M5) | Le service est opérationnel pour les agents avec Bearer seul |
| Sync triggers | Polling cron uniquement au MVP, webhook en post-MVP | Surface réseau minimale, suffisant pour des dépôts qui changent peu |
| Providers d'embedding | OpenAI + Voyage AI + Ollama dès le MVP | Valide l'abstraction `EmbeddingProvider` sur 3 cas réels |
| `.env.example` | Nettoyé strictement aux specs | Suppression `RAG_HMAC_KEY`, `RAG_ADMIN_LOCAL_*`, `RAG_LISTMONK_*`, `RAG_KEYCLOAK_*` |
| Caddyfile | Reverse proxy HTTP simple : `/api/*` → backend, `/ui*` → frontend | Pas de TLS interne, le LXC est derrière Cloudflare Tunnel |
| Observabilité | structlog JSON à stdout au MVP, Alloy en jalon dédié (M6) | Zéro impact sur le code applicatif |
| Tests DB | testcontainers-python (`pgvector/pgvector:pg16` éphémère par session pytest) | Isolation totale, marche en local et sur LXC |
| `SecretResolver` | Complet (`${env://}` + `${vault://}` avec SDK Harpocrate) dès le MVP | Conforme à `vault.md`, pas de fallback dégradé |
| Règle d'auth | **Séparation totale** : `/ui*` → JWT only, `/api*` → API key only | Aucun endpoint n'accepte les deux types de token |

---

## 1. Architecture globale

Le service est un **monolithe FastAPI** qui héberge à la fois l'API HTTP et le sync worker (asyncio background task lancé dans le `lifespan` de l'app). Un seul container `rag-backend`. Pas de Celery, pas de RQ, pas de cron externe.

```
                  ┌───────────────────────────────────────────────────┐
                  │              container rag-backend                │
                  │  ┌─────────────────────────────────────────────┐  │
                  │  │  FastAPI app (uvicorn)                      │  │
                  │  │  ┌─────────────┐  ┌────────────────────┐    │  │
                  │  │  │  routers    │  │ services métier    │    │  │
                  │  │  │  health     │──│ workspace lifecycle│    │  │
   curl /api/*    │  │  │  admin      │  │ job orchestrator   │    │  │
   ──────────────▶│  │  │  workspace  │  │ indexer engine     │    │  │
                  │  │  │  mcp        │  │ search engine      │    │  │
                  │  │  │  ui-api     │  └──────────┬─────────┘    │  │
                  │  │  └─────┬───────┘             │              │  │
                  │  │        │  api_key / JWT      │              │  │
                  │  │        ▼                     ▼              │  │
                  │  │  ┌──────────────────────────────────────┐   │  │
                  │  │  │  db.pool (asyncpg, helpers SQL)      │   │  │
                  │  │  └─────────────┬────────────────────────┘   │  │
                  │  │                ▼                            │  │
                  │  └──────────────────────────────────────────────┘ │
                  │  ┌─────────────────────────────────────────────┐  │
                  │  │  sync worker (asyncio Task, lancé par le    │  │
                  │  │  lifespan FastAPI) — polling cron des       │  │
                  │  │  workspace_sources git, déclenche les       │  │
                  │  │  index_jobs via le job orchestrator         │  │
                  │  └─────────────────────────────────────────────┘  │
                  │  ┌─────────────────────────────────────────────┐  │
                  │  │  SecretResolver (env:// + vault://)         │  │
                  │  │  cache RAM, invalidation 401/403            │  │
                  │  └─────────────────────────────────────────────┘  │
                  └───────────────────────────────────────────────────┘
                              │             │              │
                              ▼             ▼              ▼
                       ┌──────────┐ ┌──────────────┐ ┌─────────────┐
                       │ postgres │ │ Harpocrate   │ │ OpenAI/     │
                       │ rag_config│ │ vault.yoops  │ │ Voyage/     │
                       │ + rag_*   │ │              │ │ Ollama      │
                       └──────────┘ └──────────────┘ └─────────────┘
```

### Choix de design clés

1. **Sync worker dans le même process** — asyncio task lancé au `lifespan`. Job orchestrator partagé entre `push`, `manual`, `schedule` (et plus tard `webhook`).
2. **Une seule queue de jobs** (table `index_jobs`). Lock via `SELECT … FOR UPDATE SKIP LOCKED`. Préparé pour le scale horizontal sans refacto.
3. **Une base pgvector par workspace** (`rag_{workspace_name}`). Deux pools asyncpg : un sur `rag_config` (permanent), un par workspace (créé à la volée, cache LRU).
4. **Indexer engine et search engine découplés du transport HTTP** — routers fins, logique dans `services/`.
5. **SecretResolver injectable, paresseux, jamais persisté** — cache RAM TTL 5 min + invalidation 401/403.

### Règle d'auth stricte

Trois familles de routes, trois middlewares d'auth indépendants, mêmes services métier en dessous :

```
/api/admin/workspaces/...        ← Bearer api_key (master)    — curl, agents, init-rag.sh
/api/workspaces/{name}/index     ← Bearer api_key (workspace) — agents (push)
/api/mcp                         ← Bearer api_key (workspace) — Claude Code, agents
/ui                              ← JWT OIDC                    — page React
/ui-api/workspaces/...           ← JWT OIDC + rôle (rag-admin/rag-viewer)
/ui-api/jobs                     ← JWT OIDC                    — front
/health, /version                ← public
```

**Aucun endpoint n'accepte les deux types de token.** Spec drift à corriger : `specs/10-auth.md` ligne 146 retire l'accept-both sur `/workspaces/{name}/jobs`.

---

## 2. Modèle de données détaillé

### Base `rag_config` (centrale, créée par migrations)

Schéma SQL brut versionné dans `backend/migrations/`, runner Python custom (pas Alembic).

```
backend/migrations/
├── 001_init.sql                 -- extensions pgcrypto, tables workspaces + indexer_configs + schema_migrations
├── 002_workspace_sources.sql    -- sources git + JSONB config
├── 003_jobs.sql                 -- index_jobs + indexed_documents
└── 004_oidc.sql                 -- oidc_config (table créée maintenant, peuplée en M5)
```

Tables conformes aux specs 01 et 10, **trois additions** :

| Addition | Table | Justification |
|---|---|---|
| `schema_migrations(version TEXT PK, applied_at)` | nouvelle | Trace les migrations appliquées (standard) |
| `workspaces.sync_interval_seconds INT DEFAULT 300` | workspaces | Polling cron par workspace (décision question 3) |
| `workspace_sources.next_sync_at TIMESTAMPTZ` | workspace_sources | Calculé par le sync worker pour planifier sans relire toute la conf |

### Index importants

```sql
CREATE INDEX idx_workspaces_name ON workspaces(name);
CREATE INDEX idx_jobs_status_workspace ON index_jobs(status, workspace_id);
CREATE INDEX idx_sources_next_sync ON workspace_sources(next_sync_at)
  WHERE next_sync_at IS NOT NULL;
CREATE UNIQUE INDEX idx_docs_ws_path ON indexed_documents(workspace_id, path);
```

### Bases `rag_{workspace_name}` (une par workspace)

```sql
CREATE DATABASE rag_<name>;
\c rag_<name>
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE embeddings (
  id          SERIAL PRIMARY KEY,
  path        TEXT NOT NULL,
  chunk_index INT NOT NULL,
  content     TEXT NOT NULL,
  embedding   vector(<N>),
  indexed_at  TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX ON embeddings(path, chunk_index);
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

La dimension `<N>` est **interpolée littéralement** dans le SQL, whitelistée sur `{768, 1024, 1536, 3072, 4096}` pour blinder l'injection. Mapping provider/modèle → dimension dans `indexer/providers/dimensions.py`.

### Couche d'accès — pas SQLAlchemy

```
db/
├── pool.py           # AsyncpgPool factory : pool config + cache LRU pour pools workspaces
├── helpers.py        # fetch_one, fetch_all, execute, transaction context manager
├── migrations.py     # runner SQL idempotent
├── workspaces.py     # repository — pure I/O sur rag_config
├── indexer_configs.py
├── sources.py
├── jobs.py
└── documents.py
```

Les repositories exposent uniquement des fonctions async I/O. Les services dans `services/` orchestrent ces repositories + les autres modules (indexer, secrets, providers).

### Validation pgvector dimension change

Le `PATCH /workspaces/{name}` qui change provider/model :
1. Lookup `current.dimension` vs `requested.dimension`.
2. Si égales → update libre.
3. Si différentes ET `embeddings` non vide → `409 indexer_change_requires_reindex` (spec 02).
4. Si différentes ET `?confirm=true` → DROP TABLE embeddings + recréation avec nouvelle dimension + invalidation `indexed_documents` (truncate hashes) + déclenche job de réindex complète.

---

## 3. Flux clés

### Flux A — Push synchrone (`POST /api/workspaces/{name}/index`)

```
Agent ──(Bearer ws_key)──▶ api/workspace.py
                                │
                                ▼
                          auth.workspace_bearer  ── vérifie hash bcrypt vs workspaces.api_key_hash
                                │
                                ▼
                          services/indexer_service.index_document(workspace, path, content)
                                │
                                ├─▶ SHA-256(content) = h
                                ├─▶ db.documents.get_hash(workspace_id, path) == h ?
                                │     ├─ oui → return {status:"skipped"}            (zéro embed)
                                │     └─ non →
                                │           1. indexer/engine.chunk(content)        (splitter par taille)
                                │           2. resolver.resolve(api_key_ref)        (lazy, RAM only)
                                │           3. provider.embed_batch(chunks)         (HTTPX async, batch)
                                │           4. pgvector.upsert_chunks(path, chunks, vectors)
                                │           5. db.documents.upsert_hash(workspace_id, path, h, indexer_used)
                                │           6. db.jobs.insert(triggered_by="push", status="done", ...)
                                ▼
                          return {status:"indexed", chunks:N, hash:"sha256:..."}
```

Endpoint **bloquant** (spec 03 explicite). Embedding des chunks via `asyncio.gather` sur des batchs.

### Flux B — Sync git (polling cron)

```
sync/worker.py (asyncio task lancé au lifespan)
   │
   loop every 30s:
   ├─ SELECT source_id FROM workspace_sources WHERE next_sync_at <= now()
   │                                          FOR UPDATE SKIP LOCKED LIMIT 5
   │
   for source in due_sources:
   │
   ├─ services/git_sync.sync_source(source)
   │     │
   │     ├─ auth_token = resolver.resolve(source.config.auth_ref)
   │     ├─ git clone/fetch /tmp/rag-sync-{source_id}  (shallow, branch fixée)
   │     ├─ diff = compute_diff(last_commit_sha, current_sha)
   │     │
   │     for path in diff.added + diff.modified:
   │     │    if include/exclude globs match:
   │     │        content = read_file(path)
   │     │        services/indexer_service.index_document(workspace, path, content)
   │     │        → réutilise EXACTEMENT le chemin du push synchrone (dédup hash inclus)
   │     │
   │     for path in diff.deleted:
   │     │    delete chunks in pgvector + delete from indexed_documents
   │     │
   │     ├─ update source.last_commit_sha + last_indexed_at + next_sync_at
   │     └─ insert index_jobs(triggered_by="schedule", status="done", ...)
   │
   └─ sleep(30s)
```

**Propriétés clés** :
- Le sync worker n'embed jamais lui-même → délègue à `indexer_service.index_document`. Pas de duplication.
- `SELECT … FOR UPDATE SKIP LOCKED` permet de scaler horizontalement plus tard.
- Workspace dir cloné dans `/tmp/rag-sync-{source_id}` gardé entre itérations (fetch incrémental).

### Flux C — MCP search (`POST /api/mcp`)

```
Agent ──(Bearer ws_key, ou multi-workspaces)──▶ api/mcp.py
                                │
                                ▼
                          auth.workspace_bearer_multi  ── valide chaque (name, api_key)
                                │
                                ▼
                          services/search_service.search(workspaces, query, top_k, min_score)
                                │
                                ├─ pour chaque workspace:
                                │     indexer_cfg = db.workspaces.get_indexer(workspace_id)
                                │     vector = provider.embed(query)  -- MÊME provider/model que le workspace
                                │     results = pgvector.knn_search(...)
                                │       SQL : SELECT path, chunk_index, content, 1 - (embedding <=> $1) AS score
                                │             FROM embeddings WHERE 1 - (embedding <=> $1) >= $min_score
                                │             ORDER BY embedding <=> $1 LIMIT $top_k
                                │
                                ├─ merge + re-rank par score décroissant
                                ├─ keep top_k global
                                ▼
                          return {query, results: [...]}
```

Si workspaces avec providers différents → query embed 1× par provider distinct (memoization).

### Flux D — SecretResolver (transverse)

```
SecretResolver.resolve(ref: str) -> str
   │
   ├─ if ref matches "${env://VAR}"        → return os.environ[VAR]  (fail fast si absent)
   ├─ if ref matches "${vault://id:path}"  → return _vault_lookup(id, path)
   └─ else                                  → return ref  (valeur littérale)

_vault_lookup(api_key_id, path):
   ├─ check cache RAM (TTL 5min) → hit ? return
   ├─ client = harpocrate_clients[api_key_id]
   ├─ value = client.get_secret(path)
   ├─ cache[ref] = (value, expires_at)
   └─ return value

invalidation:
   ├─ sur 401/403 d'un provider → cache.pop(ref) ; retry une fois
   └─ sur shutdown → cache vidé explicitement
```

Logs : jamais la valeur, jamais l'identifiant Harpocrate physique. Uniquement la clé logique + le résultat (`resolved` / `cache_hit` / `failed_401`).

---

## 4. Bootstrap et configuration

### `.env.example` final

```env
# ─── PostgreSQL config (base rag_config) ─────────────────────
POSTGRES_USER=rag
POSTGRES_PASSWORD=
POSTGRES_DB=rag_config
DATABASE_URL=postgresql://rag:${POSTGRES_PASSWORD}@postgres:5432/rag_config

# Pour CREATE DATABASE des bases per-workspace
RAG_POSTGRES_ADMIN_URL=postgresql://rag:${POSTGRES_PASSWORD}@postgres:5432/postgres

# ─── Master key API (Bearer admin) ───────────────────────────
RAG_MASTER_KEY=

# ─── URL publique ────────────────────────────────────────────
RAG_PUBLIC_URL=http://192.168.10.184

# ─── Harpocrate (amorçage du SecretResolver) ─────────────────
HARPOCRATE_API_TOKEN_RAG=
HARPOCRATE_API_URL_RAG=https://vault.yoops.org

# ─── Logging ─────────────────────────────────────────────────
ENVIRONMENT=dev
LOG_LEVEL=INFO
```

Disparaissent : `RAG_HMAC_KEY`, `RAG_ADMIN_LOCAL_*`, `RAG_LISTMONK_*`, `RAG_KEYCLOAK_*`. La config OIDC vit dans la table `oidc_config` (peuplée via `POST /api/admin/oidc` en M5), avec `client_secret_ref` résolu via Harpocrate au démarrage.

### `config.py` — Pydantic Settings

```python
class Settings(BaseSettings):
    database_url: PostgresDsn
    postgres_admin_url: PostgresDsn
    rag_master_key: SecretStr
    rag_public_url: AnyHttpUrl
    harpocrate_api_keys: dict[str, HarpocrateClientConfig]
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    sync_worker_poll_interval_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")
```

`harpocrate_api_keys` est peuplée par un validator qui scan `os.environ` à la recherche de `HARPOCRATE_API_TOKEN_*` / `_URL_*`. Au moins une paire requise.

### `main.py` — lifespan FastAPI

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Logging structlog JSON
    setup_logging(settings.log_level, settings.environment)

    # 2. Pool config DB
    app.state.pools = WorkspacePoolRegistry(settings)
    app.state.pools.config_pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)

    # 3. Migrations idempotentes sur rag_config
    await run_migrations(app.state.pools.config_pool, "backend/migrations/")

    # 4. SecretResolver
    app.state.resolver = SecretResolver(api_keys=settings.harpocrate_api_keys, cache_ttl=300)

    # 5. OIDC config (optionnel, M5+)
    app.state.oidc = await load_oidc_config(app.state.pools.config_pool, app.state.resolver)

    # 6. Sync worker
    app.state.sync_task = asyncio.create_task(
        sync_worker_loop(app.state.pools, app.state.resolver)
    )

    yield

    app.state.sync_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.sync_task
    await app.state.pools.close_all()
```

### Gestion des erreurs au boot — fail fast

- `RAG_MASTER_KEY` vide → exit avec message clair
- `database_url` injoignable → 5 retries (5s entre chaque), puis exit
- Aucun `HARPOCRATE_API_TOKEN_*` → exit
- Migration KO → exit (jamais demi-état)
- OIDC config présent mais Harpocrate refuse `client_secret_ref` → log warning, IHM désactivée, API up

### Logging structlog

- JSON en `staging`/`prod` (consommable par Alloy en M6).
- Console colorée en `dev`.
- Jamais loggué : valeurs résolues, tokens `hrpv_1_*`, JWT, master_key, workspace api_keys.

### Endpoints publics

```
GET /health  → {"status":"ok"}
GET /version → {"version":"x.y.z", "git":"<sha>", "environment":"dev"}
```

Tout le reste exige une auth (selon la règle stricte).

---

## 5. Tests et qualité

### Structure

```
backend/tests/
├── conftest.py                    # fixtures globales
├── unit/                          # rapide, pas de DB ni réseau
│   ├── test_chunking.py
│   ├── test_secret_resolver.py    # mock httpx
│   ├── test_dimensions_lookup.py
│   ├── test_hash_dedup.py
│   └── test_indexer_engine_logic.py
├── integration/                   # testcontainers
│   ├── test_migrations.py
│   ├── test_workspaces_repo.py
│   ├── test_indexer_full.py
│   ├── test_sync_worker.py
│   └── test_search_engine.py
├── api/                           # TestClient httpx
│   ├── test_health.py
│   ├── test_admin_workspaces.py
│   ├── test_workspace_index.py
│   ├── test_mcp_search.py
│   └── test_auth.py
└── smoke/                         # opt-in, hors CI par défaut
    ├── test_openai_e2e.py
    ├── test_voyage_e2e.py
    └── test_ollama_e2e.py
```

### Fixtures clés

```python
@pytest_asyncio.fixture(scope="session")
async def pg_container():
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        pg.with_database("rag_config")
        yield pg.get_connection_url()

@pytest_asyncio.fixture(scope="session")
async def migrated_pool(pg_container):
    pool = await asyncpg.create_pool(pg_container)
    await run_migrations(pool, "backend/migrations/")
    yield pool
    await pool.close()

@pytest_asyncio.fixture
async def clean_db(migrated_pool):
    async with migrated_pool.acquire() as conn:
        await conn.execute("TRUNCATE workspaces, workspace_sources, index_jobs, indexed_documents CASCADE")
    yield migrated_pool

@pytest.fixture
def mock_resolver():
    resolver = SecretResolver(api_keys={}, cache_ttl=0)
    resolver._vault_lookup = lambda *a, **kw: pytest.fail("Vault lookup non mocké !")
    return resolver

@pytest.fixture
def mock_openai_provider():
    return DeterministicProvider(dimension=1536, seed_from_text=True)
```

### Discipline TDD

- Test rouge → impl → test vert → commit, ferme pour toute nouvelle fonctionnalité.
- Aucun test ne touche un vrai provider d'embedding en CI — `DeterministicProvider` hash le texte pour des vecteurs reproductibles.
- Smoke tests E2E (1 par provider) **opt-in** via `pytest -m smoke`, lancés manuellement avant clôture de jalon.

### Couverture cible

| Module | Branches | Lignes |
|---|---:|---:|
| `secrets/resolver.py` | 95% | 95% |
| `indexer/engine.py` | 90% | 95% |
| `indexer/providers/*` | 80% | 90% |
| `sync/worker.py` | 85% | 90% |
| `db/*` | 80% | 90% |
| `api/*` | 90% | 95% |
| `auth/*` | 95% | 95% |

Total visé : **≥ 90% lignes / ≥ 85% branches**.

### Lint, format, type check

- Ruff (lint + format), config `pyproject.toml`, règles standard + `B` + `UP`.
- `mypy --strict` sur `src/rag/`.
- Pre-commit hook : ruff check + ruff format --check + mypy. Pas de `--no-verify`.

### Quality gate par jalon

1. `ruff check src/ tests/` → 0 erreur
2. `ruff format --check src/ tests/` → 0 diff
3. `mypy --strict src/` → 0 erreur
4. `pytest -v --cov=src/rag --cov-report=term-missing` → vert + couverture atteinte
5. `pytest -m smoke` manuel (1 par provider activé)
6. Déploiement LXC 303 + curl health + smoke E2E

Si l'un échoue → on ne livre pas.

---

## 6. Roadmap des jalons

### M1 — Fondations + auth Bearer

**Scope** :
- Squelette `backend/` : `pyproject.toml` (uv), `Dockerfile`, layout `src/rag/` complet.
- `config.py`, `logging_setup.py`, `main.py` (lifespan stub).
- `db/pool.py`, `db/helpers.py`, `db/migrations.py`.
- Migrations `001_init.sql` → `004_oidc.sql` (table créée maintenant pour préparer M5).
- `secrets/resolver.py` complet (`${env://}` + `${vault://}` via SDK Harpocrate wheel) + cache RAM + invalidation 401/403.
- `auth/bearer.py` — middleware master key.
- `api/health.py` (`/health`, `/version`).
- Fixtures pytest : `pg_container`, `migrated_pool`, `clean_db`, `mock_resolver`, `client`.

**Tests minimaux** :
- Migrations idempotentes.
- SecretResolver : env, vault, erreurs, invalidation 401.
- Auth Bearer master : 401, 200.
- `/health` répond, healthcheck OK.

**Critère** :
- `./dev-deploy.sh` sur LXC 303 → stack up, `curl /health` OK.
- Quality gate vert.

---

### M2 — Workspaces + indexer engine + push synchrone

**Scope** :
- `db/workspaces.py`, `db/indexer_configs.py`, `db/documents.py`.
- `services/workspace_service.py` (CRUD + création base pgvector + CREATE EXTENSION vector).
- `indexer/providers/base.py` (ABC), `indexer/providers/dimensions.py`.
- `indexer/providers/openai.py`, `voyage.py`, `ollama.py` (HTTPX async, batch, retry exponentiel).
- `indexer/engine.py` (chunking taille fixe paramétrable défaut 1500/200, dédup hash, orchestration).
- `services/indexer_service.py`.
- `api/admin.py` — `POST/GET/PATCH/DELETE /api/admin/workspaces` + 409 dimension change.
- `api/admin.py` — `GET /api/admin/workspaces/{name}/apikey`.
- `auth/bearer.py` — extension workspace api_key.
- `api/workspace.py` — `POST /api/workspaces/{name}/index`.

**Tests minimaux** :
- CRUD workspace E2E.
- Indexer engine : chunking déterministe, embed mocké, upsert, dédup hash.
- 409 sans `?confirm=true`, OK avec.
- `POST .../index` : 200 indexed, 200 skipped, 401, 403.
- 1 smoke E2E par provider opt-in.

**Critère** :
- Créer workspace, pousser doc, vérifier en pgvector → chunks + vecteurs présents.
- Re-pousser identique → `status:"skipped"`.

---

### M3 — Sources git + sync worker + API MCP

**Scope** :
- `db/sources.py`, `db/jobs.py`.
- `services/git_sync.py` — clone shallow, fetch incrémental, diff, include/exclude globs.
- `sync/worker.py` — boucle asyncio, SELECT FOR UPDATE SKIP LOCKED.
- `api/admin.py` — `POST/DELETE /sources`, `POST /reindex` (+ `?confirm=true`), `GET /jobs`.
- `services/search_service.py` — embed query, KNN cosine, merge multi-workspaces, re-rank.
- `api/mcp.py` — `POST /api/mcp` mono + multi.
- `auth/workspace_bearer_multi` pour multi-workspace.

**Tests minimaux** :
- Sync worker : repo git local `/tmp/`, commit initial / modif / suppression.
- Reindex `?confirm=true` change provider → table recréée + hashes invalidés + réindex.
- MCP mono : top_k, min_score, score décroissant.
- MCP multi avec providers différents : embed 1× par provider (memoization).

**Critère** :
- Source git réelle → sync → `POST /api/mcp` retourne résultats pertinents.
- Modif fichier → push → sync → MCP retourne le nouveau contenu.

---

### M4 — Caddy + init-rag.sh + nettoyage

**Scope** :
- `Caddyfile` : `/api/*` → backend, `/ui*` → frontend (404 jusqu'à M5).
- `scripts/init-rag.sh` (spec 08) idempotent.
- Nettoyage `.env.example` (suppression vars hors spec).
- Mise à jour `Install-dev.md`.
- Spec drift : `specs/10-auth.md` ligne 146 corrigée.

**Tests minimaux** :
- `init-rag.sh` testé dans container : `RAG_WORKSPACES='["a","b"]'` → `.rag-client.json` correct.
- Caddyfile : `curl :80/api/health` OK.

**Critère** :
- Stack complète up via `dev-deploy.sh`.
- `init-rag.sh` testé manuellement.

---

### M5 — OIDC + IHM

**Scope** :
- `frontend/` complet : Vite + React 18 + TS strict + react-router-dom + TanStack Query + Tailwind + shadcn/ui + i18next.
- Pages : Workspaces (list + detail), Sources, Jobs, Login.
- `auth/oidc.py` côté backend : flow OIDC code, callback `/auth/callback`, session JWT, rôles.
- `api/admin.py` — `POST /api/admin/oidc`.
- `api/ui.py` (sert le build front protégé OIDC) + `api/ui_admin.py` (endpoints JWT).
- Services réutilisés tels quels — seuls routers et middlewares diffèrent.
- Tests Vitest sur composants critiques, pytest sur flow OIDC (keycloak mocké).

**Critère** :
- Naviguer `:80/ui` → redirect Keycloak → login → workspaces visibles.
- Créer workspace via IHM → vérif SQL.
- i18n complet (fr + en).

---

### M6 — Alloy (post-MVP optionnel)

**Scope** :
- `infra/alloy-agent/docker-compose.yml`, `config.alloy`, `config-journald-only.alloy`, `.env.template`.
- `scripts/infra/deploy-alloy.sh` selon `docs/logs.md`.

**Critère** :
- Logs visibles dans Grafana avec labels `host=lxc303`, `module=rag`.

---

### Dépendances

```
M1 (fondations + Bearer)
  │
  ▼
M2 (workspaces + indexer + push)
  │
  ▼
M3 (sources git + sync + MCP)
  │
  ▼
M4 (Caddy + init-rag + cleanup)
  │
  ▼
M5 (OIDC + IHM)
  │
  ▼
M6 (Alloy, indépendant après M1)
```

Validation utilisateur entre chaque jalon. Chaque jalon livre du code testé déployé sur LXC 303.

---

## Notes hors scope du design

- **Webhooks GitHub/Azure** : post-MVP, ne touche pas l'architecture (le `triggered_by="webhook"` est déjà prévu dans `index_jobs`).
- **Sources autres que git** (url, confluence, notion, folder, s3) : roadmap spec 09, post-MVP. Le champ `workspace_sources.type` est déjà extensible.
- **Reranking** : roadmap spec 09, post-MVP.
- **Recovery mails (Listmonk)** : abandonné dans le `.env.example`, à re-spec si besoin.
- **Admin local fallback** : abandonné, à re-spec si besoin.
