# M9 — Chunking infrastructure (backend)

> **Statut** : design validé pour implémentation.
> **Spec produit ciblée** : `specs/09-roadmap.md` § « Amélioration du chunking ».
> **Prérequis** : M4a (RealIndexer + pipeline d'indexation), M8 (pattern config par workspace).
> **Hors-scope explicite** : aucun nouvel algorithme de chunking, frontend (différé en M9b), exposition `metadata` via MCP.

---

## 1. Contexte et motivation

Le chunking actuel est un algorithme unique (`backend/src/rag/indexer/chunking.py`) appelé sans paramètres explicites (`chunk_text(content)` dans `real.py:84`). Les valeurs `max_chars=2000`, `min_chars=200`, `overlap_chars=200` sont hardcodées dans la signature de fonction. Aucune différenciation par type de fichier, aucune config par workspace, aucun champ de métadonnées sur les chunks stockés.

La roadmap prévoit trois axes d'évolution :
1. Chunking sémantique Markdown (respect des sections)
2. Chunking par blocs de code
3. Métadonnées de chunk enrichies (titre de section parent, type de contenu)

Tenter de livrer les trois en un jalon serait risqué : couplage entre choix d'algos et plomberie de config. Ce jalon **livre uniquement l'infrastructure** : registry de stratégies, config par workspace, champ `metadata` sur `embeddings`, migration des bases workspace existantes, flow de reindex sur changement de config. L'algorithme actuel reste seul disponible, enregistré sous le nom `paragraph`. Les algos `markdown` et `code` arriveront en jalons distincts par-dessus cette infra.

Le **frontend (onglet « Chunking » dans `WorkspaceDetailPanel`) est hors-scope M9** — jalon **M9b** à venir, sur le pattern M8/M8b.

---

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Config **par workspace** (table dédiée `chunking_configs`) | Symétrique avec `indexer_configs` et `rerank_configs` ; permet customisation par corpus |
| D2 | Config **obligatoire** (1 row par workspace, peuplée pour les existants) | Cohérent avec `indexer_configs` (toujours présent). L'utilisateur voit toujours sa config |
| D3 | Forme `strategy TEXT + colonnes typées (max_chars, min_chars, overlap_chars) + extras JSONB` | Params communs typés (CHECK SQL + Pydantic) ; `extras` réservé aux params spécifiques des futures stratégies |
| D4 | `strategy ∈ {"paragraph"}` aujourd'hui, élargie par migration aux jalons suivants | Pas d'enum côté DB qui rendrait l'évolution coûteuse ; un simple `CHECK` qui sera relâché |
| D5 | Ajout `embeddings.metadata JSONB NOT NULL DEFAULT '{}'` **maintenant** | Évite une migration multi-bases au jalon md/code ; champ vide pour `paragraph` est gratuit |
| D6 | Migration **par base workspace** via nouveau runner idempotent | Aujourd'hui pas de mécanisme : il faut une infra. La construire ici la rend réutilisable pour tous les jalons futurs touchant au schéma workspace |
| D7 | **Boot scan** : runner exécuté au lifespan startup, fail-fast si une base échoue | Automatique sans intervention humaine ; refus de démarrer plutôt qu'état incohérent silencieux |
| D8 | **Une transaction par migration workspace** (pas une globale) | Si la migration N°3 plante, les 1 et 2 restent appliquées — pas de rollback de progrès acquis |
| D9 | Pattern **Protocol + factory** pour les chunkers | Miroir de `providers/factory.py:make_provider` ; permet l'ajout futur de stratégies sans toucher au call site `RealIndexer` |
| D10 | Restructuration `chunking.py` → package `chunking/` | Préparer l'arrivée de fichiers `paragraph.py`, `markdown.py`, `code.py` sans étouffer un fichier unique |
| D11 | `Chunk` dataclass `(content: str, metadata: dict)` au lieu de `list[str]` | Transport explicite des métadonnées de chunk à travers le pipeline ; type-safe |
| D12 | Reindex sur changement de config : **même pattern qu'indexer** (`confirm + trigger`) | `IndexerChangeRequiresReindex` existe déjà ; on ajoute son symétrique `ChunkingChangeRequiresReindex`. Pas de fallback silencieux |
| D13 | Pas d'endpoint séparé de reindex chunking : flux unique via `PUT chunking-config?confirm=true` | Symétrique avec rerank — `POST /reindex` reste cantonné au changement d'indexer |
| D14 | Pas d'exposition de `metadata` via MCP dans ce jalon | Pas de chunker qui le remplit → exposer un champ vide ne sert à personne. M9+md ouvrira le sujet |

---

## 3. Schéma BDD

### 3.1 Migration `012_chunking_configs.sql` (base `rag_config`)

```sql
-- Migration 012 — chunking_configs : config chunking par workspace (obligatoire)
--
-- 1 row par workspace. La row est créée à la création du workspace.
-- Migration peuple les workspaces existants avec la stratégie 'paragraph' + valeurs actuelles.
-- Cascade ON DELETE : suppression workspace → suppression chunking_config auto.

CREATE TABLE chunking_configs (
    workspace_id    UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    strategy        TEXT NOT NULL CHECK (strategy IN ('paragraph')),
    max_chars       INT  NOT NULL CHECK (max_chars  > 0),
    min_chars       INT  NOT NULL CHECK (min_chars  >= 0 AND min_chars < max_chars),
    overlap_chars   INT  NOT NULL CHECK (overlap_chars >= 0 AND overlap_chars < max_chars),
    extras          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Peuplement des workspaces existants avec les valeurs hardcodées actuelles.
INSERT INTO chunking_configs (workspace_id, strategy, max_chars, min_chars, overlap_chars)
SELECT id, 'paragraph', 2000, 200, 200
FROM workspaces
ON CONFLICT (workspace_id) DO NOTHING;
```

**Invariants** :
- 1 row max par workspace (PRIMARY KEY).
- `strategy ∈ {"paragraph"}` aujourd'hui. Élargi via futures migrations (`ALTER TABLE ... DROP CONSTRAINT chunking_configs_strategy_check; ADD CONSTRAINT ... CHECK (strategy IN ('paragraph','markdown','code'))`).
- `min_chars < max_chars` et `overlap_chars < max_chars` garantis SQL + Pydantic.
- `extras` doit être `{}` quand `strategy == "paragraph"` (validation Pydantic ; pas de contrainte SQL).
- Pas de trigger `updated_at` (convention projet : géré au niveau service).

### 3.2 Migration `013_index_jobs_chunking_change_trigger.sql` (base `rag_config`)

Élargissement de la `CHECK` constraint sur `index_jobs.triggered_by` pour accepter la valeur `'reindex_chunking_change'`.

Pattern hérité de `007_index_jobs_reindex_trigger.sql` :
```sql
ALTER TABLE index_jobs DROP CONSTRAINT index_jobs_triggered_by_check;
ALTER TABLE index_jobs ADD CONSTRAINT index_jobs_triggered_by_check
    CHECK (triggered_by IN ('manual','webhook','push','schedule',
                            'reindex_indexer_change','reindex_chunking_change'));
```

### 3.3 Nouvelle infra `workspace_migrations/` (par base workspace)

Nouvelle table créée **dans chaque base workspace** par le runner au premier passage :

```sql
CREATE TABLE IF NOT EXISTS workspace_schema_migrations (
    version    INT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.4 Migration workspace `001_embeddings_metadata.sql`

```sql
ALTER TABLE embeddings
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
```

Idempotente (`IF NOT EXISTS`). Applicable :
- aux bases workspace existantes au boot,
- à une base fraîchement créée (la column existe déjà via `create_embeddings_table` mis à jour — l'`ALTER ... IF NOT EXISTS` est no-op).

### 3.5 Évolution `create_embeddings_table`

`backend/src/rag/db/workspace_schema.py` : ajout du champ `metadata` directement dans le `CREATE TABLE embeddings` initial pour les nouveaux workspaces.

```sql
CREATE TABLE embeddings (
    id           SERIAL PRIMARY KEY,
    path         TEXT NOT NULL,
    chunk_index  INT  NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector({dimension}) NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    indexed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (path, chunk_index)
);
```

---

## 4. Composants applicatifs

### 4.1 Restructuration `chunking.py` → package `chunking/`

```
backend/src/rag/indexer/chunking/
├── __init__.py              # re-export: Chunk, ChunkerProtocol, make_chunker
├── protocol.py              # ChunkerProtocol + dataclass Chunk
├── paragraph.py             # ParagraphChunker (algo actuel, déplacé)
└── factory.py               # make_chunker(strategy, **params) -> ChunkerProtocol
```

**`protocol.py`** :

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Chunk:
    content: str
    metadata: dict[str, Any]   # vide pour ParagraphChunker ; rempli par stratégies futures


class ChunkerProtocol(Protocol):
    def chunk(self, content: str) -> list[Chunk]: ...
```

**`paragraph.py`** : `ParagraphChunker(max_chars, min_chars, overlap_chars)` encapsule l'algo actuel de `chunking.py`. La logique reste identique (paragraphes → coalesce → split gros → overlap). La méthode `chunk()` renvoie `list[Chunk]` avec `metadata={}` pour chaque chunk.

**`factory.py`** :

```python
def make_chunker(
    *,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> ChunkerProtocol:
    if strategy == "paragraph":
        if extras:
            raise ValueError(f"paragraph strategy does not accept extras (got {extras!r})")
        return ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )
    raise ValueError(f"unknown chunking strategy: {strategy}")
```

### 4.2 Service `services/chunking_configs.py`

CRUD asyncpg pur, miroir de `services/rerank_configs.py`.

```python
async def get_chunking_config(
    pool: asyncpg.Pool, *, workspace_id: UUID,
) -> ChunkingConfigRow: ...

async def upsert_chunking_config(
    pool: asyncpg.Pool,
    *,
    workspace_id: UUID,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> ChunkingConfigRow: ...
```

Pas de `delete` : la row est obligatoire et liée au cycle de vie workspace via FK cascade.

### 4.3 Hook création workspace

`services/workspaces.py:create_workspace` étendu pour, **dans la même transaction** que la création de la row `workspaces` :
1. INSERT dans `chunking_configs` avec `(strategy='paragraph', max_chars=2000, min_chars=200, overlap_chars=200, extras='{}')`.

Puis, après `create_embeddings_table(workspace_dsn, dimension=...)` :
2. `apply_pending(workspace_dsn)` — exécute le runner pour insérer `(version=1, applied_at=now())` dans `workspace_schema_migrations`. La migration 001 est idempotente, donc no-op si la column existe déjà.

### 4.4 `RealIndexer` adapté

`backend/src/rag/indexer/real.py` :
- `_load_workspace_context` étend son `SELECT` avec un JOIN sur `chunking_configs` pour récupérer `strategy, max_chars, min_chars, overlap_chars, extras`.
- Dans `index_file`, remplacement de `chunks = chunk_text(content)` par :

```python
chunker = make_chunker(
    strategy=ctx["chunking_strategy"],
    max_chars=ctx["chunking_max_chars"],
    min_chars=ctx["chunking_min_chars"],
    overlap_chars=ctx["chunking_overlap_chars"],
    extras=ctx["chunking_extras"],
)
chunks: list[Chunk] = chunker.chunk(content)
```

- L'appel à `provider.embed_texts(...)` prend désormais `[c.content for c in chunks]`.
- L'appel à `upsert_chunks(...)` prend désormais `list[Chunk]` (cf. §4.5).

### 4.5 `workspace_embeddings.upsert_chunks` adapté

Signature changée :

```python
async def upsert_chunks(
    workspace_pool: asyncpg.Pool,
    *,
    path: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> int:
    ...
    records = [
        (path, idx, chunk.content, embedding, chunk.metadata)
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
    ]
    await conn.executemany(
        "INSERT INTO embeddings (path, chunk_index, content, embedding, metadata) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        records,
    )
```

Casse légère acceptable : un seul appelant interne (`RealIndexer`).

### 4.6 Reindex flow : `services/jobs.py`

Nouvelle fonction `apply_chunking_change(*, name, payload, confirm, config_pool, ...)` :
1. Charge la config actuelle.
2. Si payload identique à la config actuelle → return `None` (le caller renverra 204).
3. Sinon, compte les `indexed_documents` du workspace :
   - `docs == 0` → `upsert_chunking_config(...)` + return `("updated", new_config)` (le caller renverra 200).
   - `docs > 0 and not confirm` → `raise ChunkingChangeRequiresReindex(...)`.
   - `docs > 0 and confirm` → en **une transaction** : `upsert_chunking_config(...)` + `create_pending_job(triggered_by='reindex_chunking_change')`. Return `("reindex_triggered", job_row)` (le caller renverra 202).

---

## 5. API REST

Tous sous `/api/admin` (auth admin existante). Pattern miroir du rerank.

### 5.1 `GET /workspaces/{name}/chunking-config`

Réponse 200 :
```json
{
  "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
  "strategy": "paragraph",
  "max_chars": 2000,
  "min_chars": 200,
  "overlap_chars": 200,
  "extras": {},
  "created_at": "2026-05-18T10:00:00Z",
  "updated_at": "2026-05-18T10:00:00Z"
}
```

404 si workspace inconnu (la config existant toujours pour un workspace valide).

### 5.2 `PUT /workspaces/{name}/chunking-config?confirm={bool}`

Payload :
```json
{
  "strategy": "paragraph",
  "max_chars": 2000,
  "min_chars": 200,
  "overlap_chars": 200,
  "extras": {}
}
```

Validation Pydantic (DTO `ChunkingConfigUpdate`) :
- `strategy: Literal["paragraph"]` (élargi aux jalons suivants)
- `max_chars > 0`, `min_chars >= 0 < max_chars`, `overlap_chars >= 0 < max_chars`
- `extras == {}` quand `strategy == "paragraph"` (futurs chunkers définiront leurs propres schémas via discriminated union)

Comportements :

| Cas | Réponse |
|---|---|
| Payload identique à la config actuelle | `204 No Content` |
| Changement réel + `indexed_documents = 0` | `200 OK` + `ChunkingConfigResponse` |
| Changement réel + `indexed_documents > 0` + `confirm=false` | `409 Conflict` + `chunking_change_requires_reindex` |
| Changement réel + `indexed_documents > 0` + `confirm=true` | `202 Accepted` + `JobResponse` (job en pending) |
| Payload invalide (regex/CHECK/règles Pydantic) | `422 Unprocessable Entity` |

Payload 409 (format aligné sur `errors.py:99`) :
```json
{
  "error": "chunking_change_requires_reindex",
  "workspace": "my-workspace",
  "current": "paragraph (max=2000, min=200, overlap=200)",
  "new": "paragraph (max=1500, min=100, overlap=150)",
  "action": "PUT /workspaces/my-workspace/chunking-config?confirm=true"
}
```

### 5.3 Pas d'endpoint `DELETE`

Suppression = `DELETE /workspaces/{name}` qui cascade via FK.

### 5.4 Pas d'extension de `POST /workspaces/{name}/reindex`

Le reindex chunking est déclenché par `PUT chunking-config?confirm=true`. L'endpoint `/reindex` reste cantonné au changement d'indexer + reindex manuel. Symétrique du rerank.

---

## 6. Boot scan & error handling

### 6.1 Runner `backend/src/rag/db/workspace_migrations/runner.py`

```python
async def apply_pending(workspace_dsn: str) -> int:
    """Applique les migrations workspace manquantes sur la base donnée.

    Idempotent. Crée workspace_schema_migrations si absente, lit la version
    courante, applique en ordre numérique les .sql > version courante, insère
    la nouvelle version après chaque succès. Retourne le nombre de migrations
    appliquées dans cet appel.
    """
```

Algorithme :
1. `CREATE TABLE IF NOT EXISTS workspace_schema_migrations(...)` — idempotent.
2. `SELECT COALESCE(MAX(version), 0)` → `current_version`.
3. Glob `versions/*.sql` triés par numéro → liste des candidates.
4. Pour chaque migration `version > current_version`, **dans une transaction par migration** :
   - lit le fichier SQL, l'exécute
   - `INSERT INTO workspace_schema_migrations(version, applied_at)`
   - commit
5. Si une migration échoue : rollback de **cette migration uniquement** + `raise` (les migrations précédentes restent appliquées).

### 6.2 Boot scan FastAPI lifespan

`backend/src/agflow/main.py` (ou module lifespan équivalent), après init `config_pool`, avant d'accepter du trafic :

```python
rows = await config_pool.fetch("SELECT name, rag_cnx FROM workspaces")
for row in rows:
    try:
        applied = await apply_pending(row["rag_cnx"])
        if applied:
            log.info("workspace_migration.applied",
                     workspace=row["name"], count=applied)
    except Exception:
        log.error("workspace_migration.failed",
                  workspace=row["name"], exc_info=True)
        raise   # fail-fast : refus de démarrer si une base est incohérente
```

### 6.3 Compensation à la création workspace

`services/workspaces.py:create_workspace` après `create_embeddings_table` appelle `apply_pending(workspace_dsn)`. Si l'appel échoue, la compensation existante (drop DB + suppression row workspaces) s'applique — pas de cas particulier à introduire.

### 6.4 Pas d'erreur silencieuse

- Échec migration au boot → `raise` au startup, Docker redémarre, l'opérateur voit le log.
- Échec migration à la création workspace → rollback de la création complète.
- Échec parsing/exécution du SQL → exception remontée, jamais avalée.

---

## 7. Tests & couverture

Pattern aligné sur `docs/tests-python.md` et la convention projet (`session_pool` + `run_migrations`, pas de trigger `updated_at`).

### 7.1 Tests unitaires (pas de DB)

| Fichier | Couvre |
|---|---|
| `tests/unit/indexer/test_chunking_paragraph.py` | Tous les tests existants de `test_chunking.py` portés sur `ParagraphChunker.chunk()`. Vérifie `Chunk.metadata == {}` |
| `tests/unit/indexer/test_chunking_factory.py` | `make_chunker(strategy='paragraph', ...)` OK ; `extras` non vide → `ValueError` ; `strategy` inconnue → `ValueError` |
| `tests/unit/schemas/test_chunking_config_schema.py` | DTO Pydantic : `max_chars > 0`, `min_chars < max_chars`, `overlap_chars < max_chars`, `strategy` enum, `extras == {}` pour paragraph |

L'ancien `tests/unit/test_chunking.py` est **déplacé/renommé** vers `tests/unit/indexer/test_chunking_paragraph.py`. Pas de duplication.

### 7.2 Tests d'intégration DB

| Fichier | Couvre |
|---|---|
| `tests/integration/test_migration_012_chunking_configs.py` | Création table, types, contraintes CHECK, peuplement workspaces existants, idempotence |
| `tests/integration/test_migration_013_chunking_trigger.py` | CHECK élargie sur `index_jobs.triggered_by` |
| `tests/integration/test_workspace_migrations_runner.py` | `apply_pending` crée la table, applique en ordre, idempotent (re-run = 0), fail-fast + transaction par migration (mock SQL qui plante) |
| `tests/integration/test_workspace_migration_001_embeddings_metadata.py` | Base existante (créée sans `metadata`) → après `apply_pending`, column présente, données préservées avec `metadata = '{}'`, re-run no-op |
| `tests/integration/test_services_chunking_configs.py` | `get_chunking_config`, `upsert_chunking_config`, FK cascade |
| `tests/integration/test_create_workspace_with_chunking.py` | `create_workspace` insère `chunking_configs` par défaut + appelle `apply_pending` + table à version 1 + `metadata` présent dans `embeddings` |

### 7.3 Tests d'intégration API

`tests/integration/api/test_chunking_config_api.py` couvre :
- GET 200 + shape correcte
- GET 404 workspace inconnu
- PUT payload identique → 204
- PUT changement + `docs=0` → 200 + config mise à jour en base
- PUT changement + `docs>0` + `confirm=false` → 409 `chunking_change_requires_reindex`
- PUT changement + `docs>0` + `confirm=true` → 202 + `JobResponse` (job pending `reindex_chunking_change`)
- PUT payload invalide (min ≥ max, strategy inconnue, extras non vide) → 422

### 7.4 Tests d'intégration indexer

`tests/integration/test_indexer_real_with_chunking_config.py` (ou extension de `test_indexer_real.py`) :
- `RealIndexer.index_file` lit la `chunking_config` du workspace
- Workspace avec `max_chars=500` → chunks produits respectent cette limite
- `embeddings.metadata = '{}'` après indexation avec `ParagraphChunker`

`test_indexer_real.py` adapté : fixtures créent une `chunking_configs` row par défaut.

### 7.5 Tests boot scan

`tests/integration/test_boot_workspace_migrations.py` :
- Démarre l'app avec 2 workspaces ayant des bases sans `metadata` column
- Après startup, les 2 bases ont `metadata` + `workspace_schema_migrations` à version 1
- Si une base est cassée (mock erreur), startup `raise` (refus de démarrer)

### 7.6 Non-régression explicite

- `tests/integration/test_mcp_*.py` : pas impacté (MCP search ne change pas de contrat, `metadata` non exposé).
- `tests/integration/test_indexer_noop.py` : pas impacté (NoOpIndexer ne touche pas aux chunks).

---

## 8. Plan de livraison et numérotation

- **M9** = ce jalon (backend chunking infra).
- **M9b** = frontend chunking (différé, hors-scope ici). Réutilisera le pattern M8b (onglet dans `WorkspaceDetailPanel`).
- **M9c+** ou jalons distincts : algos `markdown_chunker`, `code_chunker` (pas ce sprint).

Découpage de tâches au plan d'implémentation (rédigé après validation de la spec) :
1. Migration 012 + tests migration
2. Infra `workspace_migrations/` (runner + migration 001) + tests
3. Restructuration `chunking/` package + tests unitaires chunker
4. Service `chunking_configs` + tests
5. Adaptation `create_workspace` (insert default + apply_pending) + tests
6. Adaptation `RealIndexer` + `upsert_chunks` + tests
7. Migration 013 (CHECK trigger) + service `apply_chunking_change` + tests
8. Endpoints API + tests
9. Boot scan lifespan + tests

---

## 9. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| Boot scan ralenti par nombre élevé de workspaces | Migrations idempotentes très rapides (ALTER ... IF NOT EXISTS sur table existante = no-op quasi-instantané). Mesure à valider en test |
| Migration 001 lourde sur grosses bases (lock ACCESS EXCLUSIVE sur ALTER) | `ADD COLUMN ... DEFAULT '{}'::jsonb NOT NULL` en PG 11+ est métadonnée seulement (pas de réécriture). Acceptable |
| Workspaces créés en parallèle pendant un boot scan | Workspaces ajoutés post-snapshot ne seront pas migrés par CE boot scan. Cohérence : `create_workspace` exécute `apply_pending` localement, donc auto-migré. Aucun chevauchement |
| Breaking change `upsert_chunks(chunks: list[Chunk])` | Un seul appelant interne (`RealIndexer`). Casse acceptable, signature plus saine |
| Élargissement futur du CHECK `strategy` | Pattern hérité de `007_index_jobs_reindex_trigger.sql` ; documenté en D4 |
| Confusion entre migrations « rag_config » (`backend/migrations/`) et migrations « workspace » (`backend/src/rag/db/workspace_migrations/`) | Numérotations distinctes (012, 013 pour rag_config ; 001 pour workspace). Documentation explicite dans les README de chaque dossier au moment de l'implémentation |

---

## 10. Hors-scope explicite

- Aucun nouvel algo de chunking (markdown, code) — jalons distincts.
- Frontend → M9b.
- Exposition `metadata` via MCP search → futur, quand un chunker le remplit.
- API publique `/api/v1` — la config chunking n'est pas exposée hors `/api/admin`.
- Performance benchmarks de chunking — pas d'enjeu tant qu'on garde l'algo actuel.
