# Design — Visualisation des clés d'index et stratégie de versioning

**Date :** 2026-06-03  
**Statut :** approuvé  
**Scope :** backend + frontend + sync worker

---

## Contexte

Le RAG remplace actuellement toute la vectorisation d'un path à chaque mise à jour (`DELETE WHERE path + INSERT`). Il n'existe aucune interface pour consulter les clés (paths + chunks) présentes dans un workspace, ni pour modifier la stratégie d'indexation.

Cette feature ajoute :
1. Un onglet "Index" dans le workspace permettant de visualiser tous les paths indexés avec leurs chunks et versions.
2. Une stratégie `append` configurable par path : les anciens chunks sont conservés à chaque réindexation, les générations sont distinguées par `indexed_at`.
3. Une configuration déclarative via `.rag/strategy.yml` dans le repo source, qui fait autorité sur la configuration IHM.

---

## Architecture générale

```
Config DB (PostgreSQL central)
  └── path_strategies (workspace_id, path, strategy, updated_at, updated_by)

Workspace DB (PostgreSQL par workspace)
  └── embeddings (path, chunk_index, content, embedding, metadata, indexed_at)
      indexed_at sert de version-tag en mode append
```

### Flux d'indexation modifié

```
RealIndexer.index_file()
  1. Charge le contexte workspace (inchangé)
  2. [NEW] Lit la stratégie du path depuis path_strategies (défaut: replace)
  3. Chunke + embed (inchangé)
  4. replace → DELETE WHERE path + INSERT  (comportement actuel)
     append  → INSERT uniquement (pas de DELETE, indexed_at = now())
  5. UPDATE indexed_documents (inchangé)
```

### Flux de lecture `.rag/strategy.yml`

```
SyncWorker (après git pull, avant boucle d'indexation)
  1. Cherche .rag/strategy.yml dans le repo (absent = OK, tout reste replace)
  2. Parse YAML → dict[path, strategy]
  3. UPSERT batch dans path_strategies avec updated_by='strategy_file'
  4. Les valeurs fichier écrasent silencieusement les valeurs IHM
```

### Format `.rag/strategy.yml`

```yaml
strategies:
  LESSONS.md: append
  docs/CHANGELOG.md: append
```

Paths = chemins exacts relatifs à la racine du repo. Pas de glob dans cette version.

---

## Modèle de données

### Nouvelle table config DB

```sql
CREATE TABLE path_strategies (
    workspace_id  UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    path          TEXT        NOT NULL,
    strategy      TEXT        NOT NULL DEFAULT 'replace'
                              CHECK (strategy IN ('replace', 'append')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by    TEXT        NOT NULL DEFAULT 'ui'
                              CHECK (updated_by IN ('ui', 'strategy_file')),
    PRIMARY KEY (workspace_id, path)
);
```

`updated_by` permet à l'IHM d'afficher un badge "défini par fichier" et de désactiver le toggle quand la valeur vient de `strategy.yml`.

### Table `embeddings` — aucune modification

`indexed_at TIMESTAMPTZ DEFAULT now()` est déjà présent. En mode `append`, chaque batch insère avec le `now()` de l'appel → les chunks d'un même run partagent le même `indexed_at` et constituent une "version".

---

## Backend

### Endpoints

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/admin/workspaces/{name}/index-keys` | Liste paths indexés avec stratégie + stats |
| `GET` | `/api/admin/workspaces/{name}/index-keys/{path:path}` | Chunks d'un path, groupés par version |
| `PATCH` | `/api/admin/workspaces/{name}/index-keys/{path:path}/strategy` | Modifie la stratégie via IHM |

`{path:path}` = paramètre FastAPI acceptant les slashes.

### Schémas Pydantic

```python
class PathStrategyEntry(BaseModel):
    path: str
    strategy: Literal["replace", "append"]
    updated_by: Literal["ui", "strategy_file"]
    chunk_count: int
    version_count: int
    last_indexed_at: datetime | None

class IndexKeysResponse(BaseModel):
    paths: list[PathStrategyEntry]
    total: int

class ChunkEntry(BaseModel):
    chunk_index: int
    content: str
    metadata: dict[str, Any]
    indexed_at: datetime

class VersionGroup(BaseModel):
    indexed_at: datetime
    chunks: list[ChunkEntry]

class PathDetailResponse(BaseModel):
    path: str
    strategy: Literal["replace", "append"]
    updated_by: Literal["ui", "strategy_file"]
    versions: list[VersionGroup]  # du plus récent au plus ancien

class StrategyPatchRequest(BaseModel):
    strategy: Literal["replace", "append"]
```

### Implémentation `GET /index-keys`

Requête sur `indexed_documents` (config DB) jointée avec `path_strategies`. Pour les stats (`chunk_count`, `version_count`, `last_indexed_at`), requête agrégée sur la table `embeddings` du workspace DB via le `pool_registry`. Les paths présents dans `indexed_documents` mais absents de `path_strategies` sont retournés avec `strategy='replace', updated_by='ui'`.

### Implémentation `GET /index-keys/{path}`

Requête sur `embeddings` du workspace DB. Résultats triés par `indexed_at DESC`, groupés en `VersionGroup`. En mode `replace`, il y a toujours au plus une version.

### Implémentation `PATCH .../strategy`

UPSERT dans `path_strategies` avec `updated_by='ui'`. Idempotent. La modification est toujours acceptée au niveau API — `updated_by` repasse à `'ui'`. Le toggle est disabled dans l'IHM quand la valeur vient du fichier (UX guidance, pas enforcement API), car le prochain sync réécrasera la valeur.

### Modification `upsert_chunks`

```python
async def upsert_chunks(
    workspace_pool,
    *,
    path: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    strategy: Literal["replace", "append"] = "replace",  # NEW
) -> int:
    ...
    # Si replace : DELETE WHERE path (comportement actuel)
    # Si append  : pas de DELETE
```

### Lecture `strategy.yml` dans le sync worker

Nouvelle fonction `parse_strategy_file(repo_path: Path) -> dict[str, str]` dans `sync/worker.py` (ou module dédié `sync/strategy_config.py`). Appelée après le git pull, avant la boucle d'indexation. Fait un UPSERT batch dans `path_strategies`.

---

## Frontend

### Emplacement

Nouvel onglet "Index" dans `WorkspaceDetailPanel`, après l'onglet "Jobs".

### Structure `WorkspaceIndexTab`

```
WorkspaceIndexTab
  ├── Barre de recherche (filtre local sur path)
  ├── WorkspaceIndexKeyList
  │   └── PathRow (accordéon par path)
  │       ├── pill stratégie : "replace" (gris) | "append" (bleu)
  │       ├── badge "via fichier" si updated_by=strategy_file
  │       ├── stats : N chunks · V versions · date relative
  │       ├── Toggle switch → PATCH .../strategy
  │       │   (disabled + tooltip si updated_by=strategy_file)
  │       └── [expanded] VersionGroup(s)
  │           └── Section par indexed_at (label date+heure)
  │               └── ChunkCard : index | extrait content | metadata JSON
  └── Pagination si > 50 paths
```

### Comportement du toggle

- `updated_by = 'strategy_file'` → toggle disabled, tooltip : "Défini par `.rag/strategy.yml` — modifiable uniquement dans le fichier"
- `updated_by = 'ui'` → toggle actif, PATCH immédiat avec optimistic update

### Hooks React Query

```typescript
useIndexKeys(workspaceName: string)
  → GET /api/admin/workspaces/{name}/index-keys

useIndexKeyDetail(workspaceName: string, path: string, enabled: boolean)
  → GET /api/admin/workspaces/{name}/index-keys/{path}
  // enabled=isOpen : chargement lazy à l'ouverture de l'accordéon

usePatchStrategy(workspaceName: string)
  → PATCH /api/admin/workspaces/{name}/index-keys/{path}/strategy
```

### i18n

Toutes les strings sous la clé `workspace.index.*` dans `fr.json` et `en.json`.

---

## Tests

### Backend

- `test_path_strategies_crud` : UPSERT, lecture, cascade DELETE workspace
- `test_upsert_chunks_replace` : comportement actuel préservé (DELETE + INSERT)
- `test_upsert_chunks_append` : pas de DELETE, deux batches → deux versions distinctes
- `test_index_keys_endpoint` : GET liste, pagination, paths sans stratégie explicite → replace
- `test_index_key_detail_endpoint` : GET chunks groupés par version
- `test_patch_strategy_endpoint` : PATCH, idempotence
- `test_parse_strategy_file` : YAML valide, absent, clés inconnues ignorées
- `test_sync_worker_applies_strategy_file` : integration — strategy.yml écrase la valeur UI

### Frontend

- `WorkspaceIndexTab` : rendu liste, filtre, pagination
- `PathRow` : toggle disabled si strategy_file, optimistic update si ui
- Hooks : mock React Query, cas erreur réseau
