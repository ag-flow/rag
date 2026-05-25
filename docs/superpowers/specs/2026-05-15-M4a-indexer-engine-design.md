# M4a — Indexer Engine effectif · Design

> **Statut** : design validé, prêt pour rédaction du plan d'implémentation TDD.
> **Précédent** : M3 (sync worker + scheduling git) — tag `m3-done`.
> **Suivant après M4a** : M4b (API push synchrone `POST /workspaces/{name}/index`), puis M4c (API MCP search `POST /mcp`).

## Objectif

Remplacer `NoOpIndexer` (stub M3) par un **`RealIndexer`** qui réalise effectivement le chunking + l'embedding via providers (OpenAI, Voyage AI, Ollama) + l'upsert pgvector dans la base `rag_<workspace>` dédiée. Le `SyncWorker` (M3) consomme l'`IndexerProtocol` inchangé — aucune modification du worker requise.

À la fin de M4a :
- Le `RealIndexer` est instancié au lifespan FastAPI et injecté au `SyncWorker`.
- À chaque sync git, les fichiers modifiés sont chunkés, embedded via le provider configuré du workspace, et insérés dans `rag_<workspace>.embeddings`.
- Les compteurs `files_changed` reflètent les indexations effectives.
- La déduplication SHA-256 (M3) continue de fonctionner pour skipper les fichiers inchangés.
- Aucun nouveau endpoint API n'est ajouté. Le service est utilisable via le sync git ; le push synchrone et la recherche MCP arrivent en M4b/M4c.

## Scope assumé

| Inclus M4a | Hors M4a |
|---|---|
| `chunking.py` (paragraphe + taille max + overlap) | API push synchrone `POST /workspaces/{name}/index` (M4b) |
| `providers/protocol.py` + 3 providers (OpenAI, Voyage, Ollama) | API MCP search `POST /mcp` (M4c) |
| `providers/factory.py` (dispatch provider) | Reranking (Cohere/Voyage) — M4+ |
| `db/workspace_embeddings.py` (upsert/delete chunks pgvector) | Chunking sémantique markdown — M4+ |
| `RealIndexer` orchestrant chunking + embed + upsert | Tokenizer (tiktoken) — M4+ |
| Intégration `main.py` lifespan : `RealIndexer` remplace `NoOpIndexer` | Auth workspace api_key (Bearer) — M4b |
| Tests unit avec `httpx.MockTransport` | Pool de workers concurrents — M3+ (déjà noté) |
| Tests smoke opt-in (`@pytest.mark.smoke`) pour providers réels | Reindexing manuel via API push — M4b |
| Dépendance `pgvector-python` pour sérialisation vector | |

---

## Décisions arbitrées (brainstorming 2026-05-15)

| Décision | Choix |
|---|---|
| Granularité M4 | M4a/M4b/M4c séparés ; M4a = engine, M4b = push sync, M4c = MCP search |
| Chunking | Paragraphe (`split \n\n`) + coalesce < 200 chars + split > 2000 chars + overlap 200 chars |
| Provider arch | `EmbeddingProvider` Protocol + 3 fichiers + factory dispatch |
| HTTP client | `httpx.AsyncClient` (déjà en deps M1) |
| Batching | OpenAI / Voyage : 100 textes / call max. Ollama : 1 texte / call (mono-API) |
| Retry | 1 tentative supplémentaire sur HTTP 429/503/timeout après `sleep 2s` |
| Upsert pgvector | `DELETE FROM embeddings WHERE path=$1` puis INSERT batch dans une transaction |
| Sérialisation vector | Dépendance `pgvector-python` (à ajouter `pyproject.toml`) |
| Tests providers | Mocks `httpx.MockTransport` par défaut + smoke `@pytest.mark.smoke` opt-in |
| Intégration M3 | `RealIndexer` remplace `NoOpIndexer` au lifespan ; `IndexerProtocol` inchangé |
| Tokenizer | Pas en M4a (chunking en chars). `tiktoken` à ajouter si retrieval V1 décevant |

---

## Architecture

### Composants

```
backend/src/rag/
├── indexer/
│   ├── protocol.py             # M3 (inchangé)
│   ├── noop.py                 # M3 (gardé pour tests qui ne nécessitent pas d'embeddings réels)
│   ├── chunking.py             # NEW M4a — chunk_text(content) → list[str]
│   ├── real.py                 # NEW M4a — RealIndexer (orchestration)
│   └── providers/
│       ├── __init__.py         # NEW (vide)
│       ├── protocol.py         # NEW — EmbeddingProvider Protocol + exceptions
│       ├── openai.py           # NEW — OpenAIProvider
│       ├── voyage.py           # NEW — VoyageProvider
│       ├── ollama.py           # NEW — OllamaProvider
│       └── factory.py          # NEW — make_provider(provider, model, api_key, base_url)
├── db/
│   └── workspace_embeddings.py # NEW M4a — upsert_chunks / delete_chunks_for_path / delete_path
└── main.py                     # MODIFY — RealIndexer remplace NoOpIndexer au lifespan
```

### Frontières

```
SyncWorker (M3, inchangé)
    └─ Executor (M3, inchangé)
          └─ indexer.index_file(workspace_id, path, content, content_hash, indexer_used)
                ↓ (IndexerProtocol inchangé)
          RealIndexer.index_file (M4a)
                ├─ _load_workspace_context(workspace_id)  # 1 SELECT JOIN
                ├─ chunks = chunking.chunk_text(content)
                ├─ token = secret_resolver.resolve_with_retry(${vault://rag:<api_key_ref>})
                ├─ provider = factory.make_provider(provider, model, api_key, base_url)
                ├─ embeddings = await provider.embed_texts(chunks)
                ├─ ws_pool = pool_registry.get_workspace_pool(workspace_name, rag_cnx)
                ├─ workspace_embeddings.upsert_chunks(ws_pool, path, chunks, embeddings)
                └─ UPDATE indexed_documents (config_pool)
```

L'`IndexerProtocol` reste à 2 méthodes (`index_file`, `delete_file`). Le `SyncWorker` ne sait pas si l'implémentation injectée est `NoOpIndexer` ou `RealIndexer` — substituabilité totale.

### Dépendances nouvelles (`pyproject.toml`)

```toml
[project]
dependencies = [
    ...
    "pgvector>=0.3",     # NEW M4a — sérialisation list[float] → vector(N)
    # httpx déjà en deps M1
]
```

### Settings (`config.py`)

Aucun nouveau setting pour M4a. Tout vient de `indexer_configs` (par workspace) :
- `provider`, `model`, `api_key_ref`, `base_url`, `dimension`

Le `base_url` peut servir pour Ollama (`http://192.168.10.80:11434`) ou pour les déploiements OpenAI-compatibles (Azure OpenAI, mistral.rs, etc.). Si NULL, on utilise les défauts hardcodés (`api.openai.com`, `api.voyageai.com`).

---

## Composant 1 — `chunking.py`

### Interface publique

```python
def chunk_text(
    content: str,
    *,
    max_chars: int = 2000,
    min_chars: int = 200,
    overlap_chars: int = 200,
) -> list[str]:
    """Découpe un texte en chunks de ~max_chars avec overlap.

    Algorithme (4 passes) :
      1. Split sur `\n\n` (paragraphes)
      2. Coalesce paragraphes < min_chars avec le suivant
      3. Split paragraphes > max_chars sur un séparateur naturel (`. `, `\n`, ` `)
         dans la fenêtre [max_chars - 200, max_chars]
      4. Ajoute overlap_chars chars du chunk précédent en tête du suivant

    Cas particuliers :
      - content vide → []
      - content <= min_chars → [content]
      - Code sans `\n\n` → fallback split sur `\n`
      - overlap_chars >= max_chars → ValueError

    Retourne list[str] non-vides.
    """
```

### Cas couverts par les tests (~10 unit)

- `chunk_text("")` → `[]`
- `chunk_text("hello")` → `["hello"]` (court, pas de split)
- 2 paragraphes courts (`"p1\n\np2"`) → `["p1\n\np2"]` (coalescés)
- 2 paragraphes longs distincts → 2 chunks avec overlap
- Paragraphe géant (3000 chars) → 2 chunks split + overlap
- Code Python (10 lignes sans `\n\n`) → 1 chunk (taille < max)
- Code Python long (5000 chars) → split sur `\n`
- Overlap : `chunks[i].startswith(chunks[i-1][-overlap_chars:])` pour `i >= 1`
- `chunk_text(content, overlap_chars=3000, max_chars=2000)` → `ValueError`
- Le total des chars (overlap déduit) reconstruit le contenu original (sanity check)

---

## Composant 2 — `providers/`

### Protocol + Exceptions (`providers/protocol.py`)

```python
class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Retourne 1 vecteur par texte d'entrée, dans le même ordre.

        Lève `EmbeddingProviderError` (ou sous-classe) sur échec.
        """


class EmbeddingProviderError(RuntimeError):
    """Base des erreurs provider."""


class EmbeddingAuthError(EmbeddingProviderError):
    """HTTP 401/403 — API key invalide ou révoquée."""


class EmbeddingRateLimited(EmbeddingProviderError):
    """HTTP 429 — rate-limited (le retry interne a échoué)."""


class EmbeddingProviderUnreachable(EmbeddingProviderError):
    """Réseau down, timeout, ou HTTP 503."""
```

### Implémentations

**OpenAI** (`providers/openai.py`) :
- Endpoint : `POST https://api.openai.com/v1/embeddings`
- Headers : `Authorization: Bearer <api_key>`
- Body : `{"model": "text-embedding-3-small", "input": [chunks...]}`
- Réponse : `{"data": [{"embedding": [...], "index": 0}, ...]}` (triée par index)
- Batch jusqu'à 100 textes / call (split en boucle si > 100, résultats concaténés dans l'ordre)
- Timeout 30s
- Retry : 1 sur 429/503/timeout après `sleep 2s` ; sinon lève l'exception typée
- Auth : `api_key` requis (`EmbeddingAuthError` si None)

**Voyage** (`providers/voyage.py`) :
- Endpoint : `POST https://api.voyageai.com/v1/embeddings`
- Headers : `Authorization: Bearer <api_key>`
- Body : `{"model": "voyage-3", "input": [chunks...], "input_type": "document"}`
- Réponse : `{"data": [{"embedding": [...]}, ...]}`
- Batch jusqu'à 128 textes / call
- `input_type="document"` (M4c utilisera `"query"` pour la recherche)
- Auth, timeout, retry : identiques à OpenAI

**Ollama** (`providers/ollama.py`) :
- Endpoint : `POST <base_url>/api/embeddings` (default `http://192.168.10.80:11434`)
- Pas d'auth (LXC homelab)
- Body : `{"model": "<model>", "prompt": "<single text>"}`
- Réponse : `{"embedding": [...]}`
- 1 texte par appel — boucle séquentielle sur la liste d'entrée
- Timeout 60s par appel (LLMs locaux plus lents)
- Retry : identique mais avec sleep 5s (réseau LAN, retry rapide acceptable)

### Factory (`providers/factory.py`)

```python
def make_provider(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
) -> EmbeddingProvider:
    """Dispatch sur provider. Lève ValueError si provider inconnu."""
    if provider == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    if provider == "voyage":
        return VoyageProvider(model=model, api_key=api_key)
    if provider == "ollama":
        return OllamaProvider(
            model=model,
            base_url=base_url or "http://192.168.10.80:11434",
        )
    raise ValueError(f"Unsupported provider: {provider}")
```

### Tests providers (~12 unit + ~3 smoke opt-in)

**Unit avec `httpx.MockTransport`** :
- OpenAI : success 200, auth 401 → `EmbeddingAuthError`, rate-limit 429 (retry-then-fail) → `EmbeddingRateLimited`, batch >100 (2 calls), timeout → `EmbeddingProviderUnreachable`, response malformée → erreur générique
- Voyage : success + assert `input_type=document` dans le body
- Ollama : success + boucle séquentielle sur 3 inputs + base_url override
- Factory : dispatch correct par `provider`, `ValueError` sur `provider="unknown"`

**Smoke `@pytest.mark.smoke`** (skip si env var absent) :
- OpenAI réel : 1 call avec 2 chunks, vérifie `len(embeddings[0]) == 1536`
- Voyage réel : idem `len(embeddings[0]) == 1024`
- Ollama réel : si `OLLAMA_TEST_URL` env défini, sinon skip

Documenté dans `backend/README.md` avec env vars `OPENAI_API_KEY_TEST` / `VOYAGE_API_KEY_TEST` / `OLLAMA_TEST_URL`.

---

## Composant 3 — `db/workspace_embeddings.py`

### Interface publique

```python
async def upsert_chunks(
    workspace_pool: asyncpg.Pool,
    *,
    path: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> int:
    """DELETE FROM embeddings WHERE path=$1, puis INSERT batch dans une transaction.

    Pré-condition : len(chunks) == len(embeddings). Lève ValueError sinon.
    Retourne le nombre de chunks insérés.
    """


async def delete_chunks_for_path(
    workspace_pool: asyncpg.Pool, path: str,
) -> int:
    """DELETE FROM embeddings WHERE path=$1. Retourne nombre supprimé."""


async def delete_path(
    workspace_pool: asyncpg.Pool, path: str,
) -> None:
    """Alias sémantique de delete_chunks_for_path pour le `delete_file` de RealIndexer."""
```

### Stratégie SQL

```sql
-- Transaction unique :
BEGIN;
DELETE FROM embeddings WHERE path = $1;
INSERT INTO embeddings (path, chunk_index, content, embedding)
    VALUES ($1, $2, $3, $4)
    -- ... batch via asyncpg.copy_records_to_table ou executemany
COMMIT;
```

`asyncpg.executemany` est privilégié à `copy_records_to_table` pour la simplicité (pas de gestion de Records ni de COPY). Les vectors sont passés en string via `pgvector-python` (`Vector` class) ou en format manuel `f"[{','.join(str(v) for v in vec)}]"` cast `$N::vector`.

### Tests intégration (~5)

Fixture étendue : créer une DB workspace test avec `vector` extension + table `embeddings(vector(1536))`. Réutiliser `pg_container` actuel + ajouter un helper `create_workspace_test_db(pool, dim)`.

- `upsert_chunks` insère N chunks
- `upsert_chunks` remplace les chunks existants pour le même path
- `upsert_chunks` réduit le nombre de chunks (path avait 5 chunks, on upsert 3 → seulement 3 restent)
- `delete_chunks_for_path` supprime tous les chunks d'un path
- `delete_chunks_for_path` idempotent sur path absent (retourne 0)

---

## Composant 4 — `RealIndexer` (`indexer/real.py`)

### Signature et initialisation

```python
class RealIndexer:
    """Implémentation `IndexerProtocol` qui :
      1. Chunke le contenu (chunking.chunk_text)
      2. Résout l'api_key du provider via SecretResolver
      3. Embed les chunks via le provider configuré
      4. Upsert les chunks dans rag_<workspace>.embeddings (transaction)
      5. UPDATE indexed_documents (config_pool)
    """

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        pool_registry: WorkspacePoolRegistry,
        secret_resolver: SecretResolver,
        provider_factory: Callable[..., EmbeddingProvider] = make_provider,
    ) -> None:
        self._config_pool = config_pool
        self._pool_registry = pool_registry
        self._secret_resolver = secret_resolver
        self._provider_factory = provider_factory
```

`provider_factory` est paramétrable pour permettre l'injection de mocks en tests (sans patcher `make_provider` globalement).

### `index_file` détaillé

```
1. Charge le contexte workspace (1 SELECT JOIN config_pool) :
   SELECT w.name AS workspace_name, w.rag_cnx,
          ic.provider, ic.model, ic.api_key_ref, ic.base_url
   FROM workspaces w
   JOIN indexer_configs ic ON ic.workspace_id = w.id
   WHERE w.id = $1

2. Chunking :
   chunks = chunk_text(content)
   if not chunks: return 0  # contenu vide

3. Résolution api_key (lazy) :
   api_key = None
   if ctx.api_key_ref:
       api_key = secret_resolver.resolve_with_retry(
           f"${{vault://rag:{ctx.api_key_ref}}}"
       )

4. Provider :
   provider_instance = provider_factory(
       provider=ctx.provider, model=ctx.model,
       api_key=api_key, base_url=ctx.base_url,
   )
   embeddings = await provider_instance.embed_texts(chunks)
   # len(embeddings) == len(chunks), len(embeddings[0]) == ctx.dimension

5. Upsert pgvector :
   ws_pool = await pool_registry.get_workspace_pool(ctx.workspace_name, ctx.rag_cnx)
   await upsert_chunks(ws_pool, path=path, chunks=chunks, embeddings=embeddings)

6. UPDATE indexed_documents (config_pool) :
   INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used, indexed_at)
   VALUES ($1, $2, $3, $4, now())
   ON CONFLICT (workspace_id, path) DO UPDATE
   SET content_hash=EXCLUDED.content_hash,
       indexer_used=EXCLUDED.indexer_used,
       indexed_at=EXCLUDED.indexed_at

7. Retour : len(chunks)
```

### `delete_file` détaillé

```
1. Charge le contexte workspace (idem)
2. ws_pool = pool_registry.get_workspace_pool(workspace_name, rag_cnx)
3. delete_path(ws_pool, path)
4. DELETE FROM indexed_documents WHERE workspace_id=$1 AND path=$2 (config_pool)
```

### Tests intégration RealIndexer (~5)

- `index_file` E2E avec provider mocké → chunks insérés en pgvector, ligne dans indexed_documents
- `index_file` deuxième appel avec contenu différent → ancien chunks remplacés (UNIQUE path enforced)
- `index_file` contenu vide → 0 chunks, pas d'INSERT, indexed_documents non touché
- `delete_file` → DELETE pgvector + DELETE indexed_documents
- `index_file` provider lève `EmbeddingAuthError` → exception propagée (le SyncWorker M3 marquera le job `error`)

---

## Modifications hors `indexer/`

### `main.py` lifespan

Remplacer dans la fonction `build_app` :

```python
# AVANT (M3) :
from rag.indexer.noop import NoOpIndexer
sync_worker = SyncWorker(
    ...,
    indexer=NoOpIndexer(registry.config_pool),
    ...
)

# APRÈS (M4a) :
from rag.indexer.real import RealIndexer
sync_worker = SyncWorker(
    ...,
    indexer=RealIndexer(
        config_pool=registry.config_pool,
        pool_registry=registry,
        secret_resolver=app.state.resolver,
    ),
    ...
)
```

`NoOpIndexer` reste dans le code pour les tests qui ne veulent pas embedder vraiment (par exemple les tests du `SyncWorker` lui-même, qui n'ont pas besoin d'appel HTTP).

### `pyproject.toml`

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "asyncpg>=0.30",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
    "httpx>=0.27",
    "bcrypt>=4.2",
    "python-multipart>=0.0.20",
    "harpocrate",
    "pgvector>=0.3",      # NEW M4a
]
```

### Aucune migration DB

Le schéma `rag_<workspace>.embeddings` existe depuis M2 (créé à `POST /workspaces`). M4a ne touche pas au schéma — il y INSERT pour la première fois.

### `backend/README.md`

Section "Tests" à étendre :
- Smoke opt-in providers : `uv run pytest -m smoke -v` avec env vars `OPENAI_API_KEY_TEST`, `VOYAGE_API_KEY_TEST`, `OLLAMA_TEST_URL` à fournir.

---

## Risques identifiés

1. **Bases workspaces ouvertes au lifespan** — `WorkspacePoolRegistry` ouvre les pools lazily. Premier appel à `get_workspace_pool` → connexion à `rag_<workspace>` ; pool gardé en cache LRU. Le LRU est dimensionné à 16 par défaut (cf. M1). Acceptable pour <16 workspaces. Augmenter via `WORKSPACE_POOL_LRU_SIZE` si besoin.

2. **Coût embedding OpenAI** — `text-embedding-3-small` ≈ **$0.02 / 1M tokens**. Un repo de 100 fichiers × 2000 chars (~500 tokens) = 50K tokens → $0.001 par sync complet. Acceptable même en sync 5 min (12 syncs/h × 24h × 30 jours ≈ $9/mois pour un repo de cette taille).

3. **Rate limits OpenAI** — 3000 RPM par compte. À 100 textes / call, on peut traiter 300K chunks/min. Largement au-dessus de notre charge.

4. **Vectors malformés** — si le provider retourne moins de dimensions que prévu (cas réseau truncated, response malformée), `pgvector` lèvera à l'INSERT. L'erreur remontera au `SyncWorker` (M3) qui marquera le job `error`. La cohérence est garantie par M2 (dimension figée à la création du workspace).

5. **Ollama lent** — `qwen2.5-coder:14b` sur CPU peut prendre 5-10s par embedding. Pour un repo de 100 fichiers × 5 chunks = 500 calls = 2500-5000s. **Inacceptable** en sync 5 min. **Mitigation** : recommander `nomic-embed-text` (768 dim, ~100ms / embed) pour Ollama. À documenter dans `specs/05-indexers.md`. Pour M4a, on accepte le comportement actuel ; si soucis observés, ajouter une limite de temps par fichier (ex: si sync > 5 min, marquer error et passer au suivant).

6. **Provider HTTP indisponible** — réseau down, API OpenAI en panne. Le job sera marqué `error` avec `error_message` provider-specific (déjà géré par M3 `_format_error`). La source n'est pas bloquée — retry au prochain cycle (M3 simple retry policy).

7. **Token leak dans les logs** — déjà géré côté git. Pour les providers, **aucun log ne doit contenir l'API key** (à valider dans les tests unit : asserter qu'aucun appel `log.info` n'inclut `api_key` dans les kwargs).

8. **Concurrence multi-job** — actuellement, le `SyncWorker` traite 1 job à la fois (single asyncio task). Si on passe à un pool de workers (M3+ extension), 2 jobs sur le même workspace tenteraient d'écrire dans le même `rag_<workspace>.embeddings`. La transaction du `upsert_chunks` protège l'atomicité par path, mais pas la cohérence inter-paths. Pour M4a, on accepte (single-worker).

9. **`pgvector-python` ajoute une dépendance** — ~3 MB pip, maintenu par les auteurs de pgvector. Alternatives : sérialisation manuelle (`f"[{','.join(...)}]"` + cast `$N::vector`). On choisit la dépendance pour la lisibilité du code et la garantie de compat avec les futures versions de pgvector. Coût acceptable.

10. **Embeddings non normalisés** — OpenAI/Voyage retournent des vectors normalisés (norme 1). Ollama non garanti. Pour la recherche cosine (`<=>` opérateur pgvector), c'est OK quelle que soit la normalisation. Pas d'action requise.

---

## Conformité CLAUDE.md

- Python 3.12, async/await, asyncpg direct (pas SQLAlchemy) ✓
- Pydantic v2 (à utiliser pour les DTOs internes provider si besoin — sinon dataclasses simples) ✓
- structlog (jamais `print`) ; tokens API jamais logués ✓
- Fichiers ≤300 lignes (chaque provider est court, ~80 lignes max) ✓
- Méthodes 5-15 lignes (split _embed_one_batch / _embed_many_batches pour OpenAI/Voyage) ✓
- Pas de quick-and-dirty : retry explicite avec exception typée, sanitization, frontière `IndexerProtocol` propre ✓
- Tests intégration sur Postgres LXC partagé + pgvector existant ✓
- Tests smoke opt-in pour providers réels (économe en quota, déterministe en CI) ✓

---

## Test plan récapitulatif

~35 nouveaux tests :

- **Unit (~22)** :
  - `chunking.chunk_text` : 10 tests
  - `providers/openai.py` : 5 tests (success, auth, rate-limit, batch >100, timeout)
  - `providers/voyage.py` : 2 tests (success + input_type)
  - `providers/ollama.py` : 3 tests (success, boucle séquentielle, base_url override)
  - `providers/factory.py` : 2 tests (dispatch + ValueError)

- **Intégration (~10)** :
  - `db/workspace_embeddings` : 5 tests (upsert, replace, reduce count, delete, idempotent)
  - `RealIndexer` : 5 tests (E2E avec provider mocké)

- **Smoke opt-in (~3)** : OpenAI/Voyage/Ollama réels, skippés par défaut

**Coverage cible** : ≥95% sur `indexer/chunking.py`, `indexer/real.py`, `indexer/providers/*`, `db/workspace_embeddings.py`.
