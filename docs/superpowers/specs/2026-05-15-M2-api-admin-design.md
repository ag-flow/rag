# M2 — API Administration · Design

> **Statut** : design validé, prêt pour rédaction du plan d'implémentation TDD.
> **Précédent** : M1 (fondations + auth Bearer master key) — tag `m1-done`.
> **Suivant après M2** : M3 (sync worker + indexer engine + résolution effective des jobs pending).

## Objectif

Livrer l'**API administration** complète du service RAG : CRUD des workspaces, gestion des sources git, planification de réindexations, registry des modèles d'embedding. Toute l'API est protégée par le Bearer master key (déjà en place via `require_master_key` M1).

À la fin du M2 :
- Un admin peut créer/modifier/supprimer des workspaces via API.
- Chaque workspace dispose de sa base pgvector dédiée (`rag_<name>`) avec la bonne dimension d'embedding.
- Les sources git sont enregistrées et leurs `auth_ref` validés au moment du POST.
- Les jobs de réindexation sont insérés en base avec status `pending`. **Aucun worker ne les exécute encore** (M3).
- Le registre des modèles supportés est alimentable runtime.

## Scope assumé

| Inclus M2 | Hors M2 |
|---|---|
| API admin (13 endpoints) | Sync worker / pickup des jobs pending (M3) |
| Création / suppression base pgvector workspace | Indexer engine effectif (M4) |
| Génération et rotation api_key workspace | OIDC / IHM React (M5) |
| Registry `model_dimensions` (CRUD) | MCP search endpoint (M4) |
| Eager validation des `api_key_ref` / `auth_ref` Harpocrate | Sources autres que `type=git` (M5+) |
| Migration 005 (model_dimensions) + 006 (index jobs) | Pagination des listings |

---

## Décisions arbitrées (brainstorming 2026-05-15)

| Décision | Choix |
|---|---|
| Granularité M2 | Monolithique (~13 endpoints livrés dans un seul jalon) |
| `api_key` workspace | One-shot à la création + endpoint `POST /rotate-apikey`. Pas de récupération possible — seul le hash bcrypt est persisté. |
| Validation refs Harpocrate | Eager hard : 422 si la ref n'existe pas, 503 si Harpocrate est down |
| Résolution dimension d'un modèle | Table `model_dimensions` en base, alimentable runtime via endpoints `/admin/models` |
| Schéma `rag_<workspace>` | Créé entièrement à `POST /workspaces` (CREATE DATABASE + EXTENSION vector + CREATE TABLE embeddings + INDEX ivfflat) |
| PATCH workspace | Modifie `indexer.api_key_ref` seulement. Tout autre champ → 422 |
| Changement provider/model | Via `POST /reindex` avec body `{indexer: ...}` et `?confirm=true` |
| DELETE workspace | `DROP DATABASE IF EXISTS rag_<name> WITH (FORCE)` puis `DELETE FROM workspaces` (CASCADE). Idempotent. |
| Cycle de vie des jobs | M2 insère des `index_jobs(status='pending')` ; M3 les exécutera |
| Sources | Uniquement `type=git` en M2 ; 422 sur tout autre type. Colonne stable, code extensible. |

---

## Surface API

Tous les endpoints requièrent `Authorization: Bearer ${RAG_MASTER_KEY}`. Réponse `401 missing_master_key` sinon (déjà géré par `require_master_key` de M1).

### Workspaces

| Méthode | Path | Description | Codes |
|---|---|---|---|
| POST | `/workspaces` | Crée workspace + base pgvector + table embeddings. Retourne `api_key` en clair **une seule fois**. | 201 / 409 (name exists) / 422 (model/ref unknown) / 503 (Harpocrate) |
| GET | `/workspaces` | Liste avec compteurs (M2 : `sources_count` réel, `documents_count=0`, `last_indexed_at=null`). | 200 |
| GET | `/workspaces/{name}` | Détail (config workspace + indexer + counts). | 200 / 404 |
| PATCH | `/workspaces/{name}` | Modifie `indexer.api_key_ref` seulement. | 200 / 404 / 422 (champ non modifiable) / 503 (ref unknown) |
| DELETE | `/workspaces/{name}` | DROP DATABASE + DELETE CASCADE. Idempotent. | 204 / 404 |
| POST | `/workspaces/{name}/rotate-apikey` | Régénère la `api_key`, retourne `{api_key}` en clair. Invalide l'ancienne. | 200 / 404 |

### Sources

| Méthode | Path | Description | Codes |
|---|---|---|---|
| POST | `/workspaces/{name}/sources` | Ajoute une source `type=git` (autres types → 422 en M2). Valide `auth_ref` via Harpocrate. | 201 / 404 / 422 / 503 |
| DELETE | `/workspaces/{name}/sources/{source_id}` | Supprime la source. | 204 / 404 |

### Réindexation / Jobs

| Méthode | Path | Description | Codes |
|---|---|---|---|
| POST | `/workspaces/{name}/reindex` | Crée `index_jobs(status='pending', triggered_by='manual')`. Si body `indexer` diffère du courant : 409 `indexer_change_requires_reindex` sauf `?confirm=true` (drop table embeddings, recreate dimension, invalide documents). | 202 / 404 / 409 |
| GET | `/workspaces/{name}/jobs` | Historique trié `started_at DESC NULLS LAST`. | 200 / 404 |

### Models registry

| Méthode | Path | Description | Codes |
|---|---|---|---|
| GET | `/admin/models` | Liste des `(provider, model, dimension)` supportés. | 200 |
| POST | `/admin/models` | Ajoute une entrée. Body `{provider, model, dimension>0}`. | 201 / 409 (existe) / 422 (validation) |
| DELETE | `/admin/models/{provider}/{model}` | Retire. Refusé `409 model_in_use` si un workspace actif utilise ce couple. | 204 / 404 / 409 |

---

## Modèle de données

### Migration 005 — `model_dimensions`

```sql
CREATE TABLE IF NOT EXISTS model_dimensions (
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    dimension   INT  NOT NULL CHECK (dimension > 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, model)
);

INSERT INTO model_dimensions (provider, model, dimension) VALUES
    ('openai', 'text-embedding-3-small', 1536),
    ('openai', 'text-embedding-3-large', 3072),
    ('voyage', 'voyage-3', 1024),
    ('voyage', 'voyage-code-3', 1024),
    ('ollama', 'qwen2.5-coder:14b', 4096),
    ('ollama', 'nomic-embed-text', 768)
ON CONFLICT DO NOTHING;
```

### Migration 006 — index pour `GET /workspaces/{name}/jobs`

```sql
CREATE INDEX IF NOT EXISTS index_jobs_workspace_started
    ON index_jobs (workspace_id, started_at DESC NULLS LAST);
```

### Tables M1 réutilisées telles quelles

`workspaces`, `indexer_configs`, `workspace_sources`, `index_jobs`, `indexed_documents`. Schémas inchangés.

### Schéma `rag_<workspace>` (créé dynamiquement)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
    id           SERIAL PRIMARY KEY,
    path         TEXT NOT NULL,
    chunk_index  INT  NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector(N) NOT NULL,    -- N = lookup model_dimensions
    indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (path, chunk_index)
);

CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops);
```

**Note ivfflat** : l'index est calibré à partir des données existantes. Sur table vide, ses centroids ne sont pas représentatifs jusqu'à un `REINDEX` après les premières insertions. Cohérent avec la spec 01-data-model.md. Une todo `# REINDEX recommandé après bootstrap initial` sera ajoutée côté indexer M4. Switch vers `hnsw` à étudier en M4 si performances dégradées (hors scope M2).

---

## Architecture code

```
backend/src/rag/
├── api/
│   ├── admin.py            # NEW — router master key (13 endpoints, ~250 LOC)
│   └── errors.py           # NEW — exceptions métier + handlers FastAPI
├── services/
│   ├── workspaces.py       # NEW — create/list/get/patch/delete/rotate
│   ├── sources.py          # NEW — add/delete
│   ├── jobs.py             # NEW — create_pending/list
│   ├── models.py           # NEW — CRUD model_dimensions
│   └── apikey.py           # NEW — generate (URL-safe 48) + bcrypt hash + verify
├── db/
│   └── workspace_schema.py # NEW — create_database/drop_database/create_embeddings_table
├── schemas/
│   └── admin.py            # NEW — Pydantic DTOs requests/responses
├── auth/                   # M1 inchangé
├── secrets/                # M1 inchangé
└── main.py                 # +1 ligne : app.include_router(build_admin_router())

backend/migrations/
├── 005_model_dimensions.sql  # NEW
└── 006_index_jobs_idx.sql    # NEW
```

### Frontières

```
api/admin.py  (routeur fin, validation Pydantic, mapping erreur → HTTP)
    └─→ services/{workspaces,sources,jobs,models}.py  (orchestration métier)
            └─→ db/{helpers,workspace_schema,pool}.py  (accès données + DDL)
            └─→ services/apikey.py                     (génération + hash + verify)
            └─→ secrets/resolver.py                    (eager validation refs)
            └─→ auth/bearer.py                         (require_master_key Depends)
```

`api/admin.py` ne contient **aucune logique métier**. Les services retournent des dataclasses/DTOs et lèvent des exceptions métier mappées par `api/errors.py`.

### Mapping exceptions → HTTP

| Exception métier | HTTP | Payload |
|---|---|---|
| `WorkspaceNotFound` | 404 | `{"error": "workspace_not_found", "name": "..."}` |
| `WorkspaceAlreadyExists` | 409 | `{"error": "workspace_already_exists", "name": "..."}` |
| `ModelNotSupported` | 422 | `{"error": "model_not_supported", "provider": "...", "model": "...", "supported": [...]}` |
| `RefNotFoundInVault` | 422 | `{"error": "ref_not_found_in_vault", "ref": "..."}` |
| `VaultUnreachable` | 503 | `{"error": "vault_unreachable"}` |
| `IndexerChangeRequiresReindex` | 409 | `{"error": "indexer_change_requires_reindex", "current": "...", "requested": "...", "documents_count": N, "action": "POST /workspaces/.../reindex?confirm=true"}` |
| `SourceNotFound` | 404 | `{"error": "source_not_found", "id": "..."}` |
| `SourceTypeNotSupported` | 422 | `{"error": "source_type_not_supported", "type": "...", "supported": ["git"]}` |
| `ModelInUse` | 409 | `{"error": "model_in_use", "provider": "...", "model": "...", "workspaces": [...]}` |
| `PatchFieldNotAllowed` | 422 | `{"error": "patch_field_not_allowed", "field": "..."}` |

Toutes ces erreurs portent un nom logique `error` stable consommable par les agents.

---

## Flows clés

### Flow A — `POST /workspaces`

```
1. Validation Pydantic du payload :
   - `name` : regex `^[a-z][a-z0-9_-]{0,62}$` (commence par une lettre, minuscules + chiffres + `_` ou `-`, longueur 1..63 — borne max alignée sur la limite Postgres pour les identifiants de base, vu qu'on en dérive `rag_<name>`)
   - `indexer.provider`, `indexer.model` : non vides
   - `rag.cnx`, `rag.base` : non vides
2. Lookup model_dimensions(provider, model) → ModelNotSupported (422) si miss
3. Résolution indexer.api_key_ref via SecretResolver
   - RefNotFoundInVault (422) si miss
   - VaultUnreachable (503) si Harpocrate down
4. Génération api_key URL-safe 48 chars + bcrypt hash (rounds=12, ~100ms acceptable)
5. TRANSACTION sur config_pool :
     INSERT INTO workspaces (name, api_key_hash, rag_cnx, rag_base)
     INSERT INTO indexer_configs (workspace_id, provider, model, api_key_ref, dimension)
6. Hors transaction (DDL non-transactionnel) sur admin_pool :
     CREATE DATABASE rag_<name>
7. Sur la nouvelle DB (pool one-shot dédié) :
     CREATE EXTENSION vector
     CREATE TABLE embeddings (... vector(N))
     CREATE INDEX USING ivfflat (embedding vector_cosine_ops)
8. Retour 201 { id, name, api_key, created_at }   ← api_key en clair UNIQUE
```

**Compensation en cas d'échec partiel** (étape 6 ou 7 fail après étape 5) :
- DELETE FROM workspaces WHERE id=...
- DROP DATABASE IF EXISTS rag_<name>

Si la compensation échoue elle-même : log structuré niveau ERROR avec `correlation_id`, retour 500 au client. Diag manuel.

### Flow B — `DELETE /workspaces/{name}`

```
1. SELECT id, name FROM workspaces WHERE name=$1 → 404 si miss
2. DROP DATABASE IF EXISTS rag_<name> WITH (FORCE)   (admin_pool, hors transaction)
3. DELETE FROM workspaces WHERE name=$1              (config_pool, CASCADE)
4. Return 204
```

Idempotent : retry sans état stale possible.

### Flow C — `POST /workspaces/{name}/reindex`

Body optionnel : `{"indexer": {"provider": "...", "model": "...", "api_key_ref": "..."}}`.

```
1. SELECT workspace + indexer_config courant → 404 si miss
2. Si body.indexer absent OU identique au courant :
     INSERT INTO index_jobs (workspace_id, triggered_by='manual', status='pending')
     Return 202 { job_id, status: 'pending' }
3. Si body.indexer diffère :
   a. Lookup nouvelle dimension dans model_dimensions
   b. Résoudre nouvelle api_key_ref via Harpocrate (eager)
   c. SELECT COUNT(*) FROM indexed_documents WHERE workspace_id=...
   d. Si count > 0 ET ?confirm=true absent → 409 IndexerChangeRequiresReindex
   e. Si confirm=true :
        Sur rag_<name> :
          DROP TABLE embeddings CASCADE
          CREATE TABLE embeddings (... vector(new_dim))
          CREATE INDEX USING ivfflat
        Sur config_pool :
          DELETE FROM indexed_documents WHERE workspace_id=...
          UPDATE indexer_configs SET provider/model/api_key_ref/dimension WHERE workspace_id=...
          INSERT INTO index_jobs (triggered_by='reindex_indexer_change', status='pending')
        Return 202 { job_id, status: 'pending' }
```

**Note d'idempotence partielle** : DROP TABLE + CREATE TABLE workspace ne sont pas dans la même transaction que l'UPDATE indexer_configs. Si crash entre les deux, la table workspace a la nouvelle dimension mais `indexer_configs` montre l'ancien modèle. Le worker M3 détectera l'incohérence (`dim_table != dim_config`) et marquera le job en error. Acceptable pour M2 — pas de crash recovery automatique.

### Flow D — `POST /workspaces/{name}/rotate-apikey`

```
1. SELECT workspace → 404 si miss
2. Génération nouvelle api_key + bcrypt hash
3. UPDATE workspaces SET api_key_hash=$1, updated_at=now() WHERE name=$2
4. Return 200 { api_key }
```

Invalide instantanément les agents qui utilisaient l'ancienne clé.

---

## Test plan

TDD strict. Référence : `docs/tests-python.md`.

### Unit (~25 tests)

- `services/apikey` : génération (longueur 48, charset URL-safe), bcrypt hash + verify (round-trip), verify timing-safe.
- `schemas/admin` : validation Pydantic — name regex, model unknown au niveau schema, defaults, payload PATCH limité.
- `api/errors` : chaque exception métier mappe au bon status code + payload.
- `db/workspace_schema` (mockés asyncpg) : structure des requêtes DDL générées.

### Intégration (~30 tests)

Fixture `pg_container` (function-scope, Postgres LXC) + nouvelle `cleanup_workspace_dbs` (drop toute DB `rag_test_ws_*` après chaque test).

- `workspace_schema` : create_database / drop_database (idempotent) / create_embeddings_table (dim variable, présence index ivfflat).
- `services/workspaces` : create avec compensation sur fail, list, get, patch (limité), delete CASCADE.
- `services/sources` : add (eager validation auth_ref mockée), delete, cascade lors du DELETE workspace.
- `services/jobs` : create pending, list ordonné, filter par workspace.
- `services/models` : CRUD, refus DELETE si utilisé par un workspace actif.
- Migration 005 + 006 : table créée, seed appliqué, INSERT ON CONFLICT idempotent, index présent.

### API E2E (~25 tests)

TestClient FastAPI, `SecretResolver` mocké (pas d'appel réel Harpocrate en CI).

- 13 endpoints × {nominal, 401 sans Bearer, 404, 422, 409 selon pertinence}.
- Scenarios métier : create → rotate → delete ; create → add source → delete source ; create → reindex sans changement → reindex avec changement (409) → reindex avec ?confirm=true (202 + job pending).

**Coverage cible** : ≥95% sur `services/`, `api/admin.py`, `schemas/admin.py`, `db/workspace_schema.py`. ≥90% global maintenu.

**Total** : ~80 nouveaux tests. Temps de run estimé : ~30s sur LXC (50 CREATE/DROP DATABASE × ~100ms + tests applicatifs).

---

## Risques identifiés

1. **CREATE/DROP DATABASE simultanés** : sérialisés par Postgres via locks brefs sur `pg_database`. Acceptable (création non hot path).
2. **`api_key` perdue par l'admin** : by-design. Mitigation = `rotate-apikey`. Documenter dans le swagger / README admin.
3. **Eager validation des refs au boot** : si Harpocrate down → 503 à la création. Cohérent avec attente "fail fast".
4. **Migration 005 sur LXC existant** : base `rag_config` du LXC a déjà 7 tables M1, le runner appliquera 005/006 idempotemment. 0 workspace existant, donc aucun risque.
5. **Pas de pagination sur `GET /workspaces`** : acceptable en M2 (<20 workspaces attendus). À ajouter si besoin.
6. **Sources `type=git` hardcodé** : extensibilité reportée à M5+. La colonne `type` reste générique en base.
7. **Tests E2E qui créent des bases** : +5s/run, acceptable. Bascule possible vers stratégie schema-only si gênant plus tard.
8. **Cas d'échec partiel à la création** : compensation manuelle ; si la compensation elle-même fail → log + 500 avec `correlation_id`. Diag à la main acceptable en M2 (faible volumétrie).

---

## Conformité CLAUDE.md

- Python 3.12, async/await, asyncpg direct (pas SQLAlchemy) ✓
- Pydantic v2 pour les DTOs ✓
- Structlog (jamais `print`) ; secrets résolus ne sont jamais logués ✓
- `api_key` workspace : aucun stockage en clair en base (seul le hash bcrypt). En clair uniquement dans la réponse HTTP de création/rotation, jamais persistée ailleurs ✓
- `api_key_ref` et `auth_ref` : clés logiques opaques stockées en base, résolution paresseuse via SecretResolver ✓
- Tests pointant le Postgres LXC partagé (refactor T18.9 M1) ✓
- Fichiers ≤300 lignes ; services SRP ; méthodes 5-15 lignes ✓
- Pas de quick-and-dirty : compensation explicite sur échec partiel, refus DELETE model en cours d'usage, etc. ✓
