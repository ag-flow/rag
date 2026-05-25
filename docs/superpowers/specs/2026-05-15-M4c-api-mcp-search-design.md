# M4c — API MCP Search : Spec de design

**Date** : 2026-05-15
**Branche** : `dev`
**Pré-requis** : M2 (auth bcrypt, workspaces), M4a (RealIndexer, providers, tables embeddings), M4b (`ApiKeyCache`, dependency pattern).

## 1. Objectif

Exposer l'endpoint `POST /mcp` décrit dans `specs/04-api-mcp.md` : un agent
ag.flow envoie une `query` en langage naturel et reçoit les chunks
sémantiquement proches issus d'un ou plusieurs workspaces. Recherche
vectorielle pgvector (`ORDER BY embedding <=> query_vec`), authentifiée
par api_key dans le body (conforme spec officielle).

## 2. Architecture

```
Agent ag.flow ─────► POST /mcp
                     body single : { workspace, api_key, query, top_k, min_score }
                     body multi  : { workspaces: [{name, api_key},...], query, top_k, min_score }
                          │
                          ▼
            Pydantic validation (DTO union strict left-to-right)
                          │
                  normalize_refs → list[McpWorkspaceRef]
                          │
                          ▼
            services.mcp.search(refs, query, top_k, min_score)
                          │
                  asyncio.gather([_search_one(ref) for ref in refs])
                  fail-fast : 1re exception annule les autres
                          │
                  per workspace :
                   1. _authenticate (ApiKeyCache, M4b)
                   2. load context (provider, model, api_key_ref, base_url, rag_cnx)
                   3. resolve api_key vault (lazy)
                   4. provider.embed_query(query) → vec[N]
                   5. ws_pool = pool_registry.get_workspace_pool(name, dsn)
                   6. vector_search(ws_pool, vec, top_k, min_score)
                          │
                          ▼
                  concat dans l'ordre des refs, items triés par score desc
                          │
                          ▼
            200 { query, results: [{workspace, indexer, path, chunk_index, content, score}, ...] }
```

## 3. Décisions de design

| Sujet | Choix | Pourquoi |
|---|---|---|
| **Auth location** | api_key dans le body (single ou par-workspace en multi) | Conforme spec officielle. Multi-workspaces nécessite plusieurs clés — le body est naturel. Risque access logs documenté comme infra (redact Caddy). |
| **embed_query API** | Méthode dédiée `embed_query(text) -> list[float]` sur `EmbeddingProvider` | Voyage utilise `input_type="query"` (meilleure qualité). OpenAI/Ollama délèguent à `embed_texts([text])[0]`. |
| **Mixed indexers** | Autorisé. Champ `indexer` dans chaque `SearchHit` permet à l'agent de connaître l'origine. | Refuser serait restrictif ; les scores ne sont pas comparables cross-indexer mais l'agent reçoit l'info. Top_k par workspace (cf. décision suivante) limite déjà la confusion. |
| **Sémantique top_k** | Par workspace (chaque workspace retourne ses top_k) | Plus simple en SQL. Pas de fusion globale. La réponse peut contenir jusqu'à `top_k * len(refs)` items. |
| **min_score filter** | Over-fetch `top_k * 4` triés par distance ivfflat + filtre Python `score >= min_score` + slice `top_k`. | pgvector best practice : `ORDER BY embedding <=> $1 LIMIT N` pour utiliser l'index ivfflat. Un `WHERE` AVANT LIMIT casse l'index. |
| **Erreur partielle** | Fail-fast (1re exception annule les autres tasks) | Simple, prévisible. Évite la confusion "résultats partiels silencieux". L'agent corrige sa config avant de re-tenter. |
| **Parallélisme** | `asyncio.gather` par workspace | Latence ~ max(workspace_latency). Coût accepté : 3 workspaces openai = 3 appels OpenAI (pas de cache embed_query inter-workspace en M4c). |
| **Format requête** | Discriminated union strict (`SingleWorkspaceRequest \| MultiWorkspaceRequest`) avec `extra="forbid"` | Pas de champ `mode` ajouté. Discrimination par champs présents (`workspace` vs `workspaces`). Mix des deux → 422. |
| **Auth cache** | Réutilise `ApiKeyCache` (M4b) tel quel | Mêmes invariants : seules les vérifications bcrypt **réussies** sont cachées. Le `rotate-apikey` invalide déjà. |

## 4. Composants

### 4.1 Nouveaux modules

| Fichier | Rôle | LOC cible |
|---|---|---|
| `backend/src/rag/schemas/mcp.py` | `SingleWorkspaceRequest`, `MultiWorkspaceRequest`, `_McpWorkspaceRef`, `SearchHit`, `McpResponse`, `McpRequest` (union). | ~80 |
| `backend/src/rag/services/mcp.py` | `McpWorkspaceRef` dataclass, `normalize_refs()`, `search()` orchestrateur, `_search_one`, `_authenticate`, `_load_workspace_context`. | ~150 |
| `backend/src/rag/db/workspace_search.py` | `vector_search(pool, query_vec, top_k, min_score, workspace_name, indexer_used) -> list[SearchHit]`. | ~50 |
| `backend/src/rag/api/mcp.py` | `build_mcp_router()` avec endpoint POST `/mcp`. | ~50 |

### 4.2 Modifications de modules existants

- `backend/src/rag/indexer/providers/protocol.py` :
  - Ajouter `async def embed_query(self, text: str) -> list[float]` au Protocol.

- `backend/src/rag/indexer/providers/openai.py` :
  ```python
  async def embed_query(self, text: str) -> list[float]:
      vectors = await self.embed_texts([text])
      if not vectors:
          raise EmbeddingProviderUnreachable("OpenAI returned empty embedding")
      return vectors[0]
  ```

- `backend/src/rag/indexer/providers/voyage.py` :
  - Refactor `_embed_batch(client, batch, *, input_type: str = "document")` (keyword-only avec défaut).
  - Ajouter `embed_query(text)` qui appelle `_embed_batch(client, [text], input_type="query")`.

- `backend/src/rag/indexer/providers/ollama.py` :
  ```python
  async def embed_query(self, text: str) -> list[float]:
      vectors = await self.embed_texts([text])
      if not vectors:
          raise EmbeddingProviderUnreachable("Ollama returned empty embedding")
      return vectors[0]
  ```

- `backend/src/rag/main.py` :
  - Import `from rag.api.mcp import build_mcp_router`.
  - `app.include_router(build_mcp_router())` après `build_workspace_router()`.

## 5. Schemas

```python
# schemas/mcp.py
from __future__ import annotations
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

_QUERY_MAX_LEN = 2000
_TOP_K_MAX = 50
_API_KEY_MAX = 128
_WORKSPACE_NAME_REGEX = r"^[a-z][a-z0-9_-]{0,62}$"


class _McpRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., min_length=1, max_length=_QUERY_MAX_LEN)
    top_k: int = Field(default=5, ge=1, le=_TOP_K_MAX)
    min_score: float = Field(default=0.7, ge=-1.0, le=1.0)


class SingleWorkspaceRequest(_McpRequestBase):
    workspace: str = Field(..., pattern=_WORKSPACE_NAME_REGEX)
    api_key: str = Field(..., min_length=1, max_length=_API_KEY_MAX)


class _McpWorkspaceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., pattern=_WORKSPACE_NAME_REGEX)
    api_key: str = Field(..., min_length=1, max_length=_API_KEY_MAX)


class MultiWorkspaceRequest(_McpRequestBase):
    workspaces: list[_McpWorkspaceRef] = Field(..., min_length=1, max_length=10)


# Union sans discriminator : Pydantic v2 smart mode tente les deux variants.
# Avec `extra="forbid"` sur chaque, un payload avec `workspace` matche
# Single (Multi rejette les champs inconnus), un payload avec `workspaces`
# matche Multi, un payload mix → aucune des deux matche → 422.
McpRequest = SingleWorkspaceRequest | MultiWorkspaceRequest


class SearchHit(BaseModel):
    workspace: str
    indexer: str       # "<provider>/<model>"
    path: str
    chunk_index: int
    content: str
    score: float       # cosine similarity


class McpResponse(BaseModel):
    query: str
    results: list[SearchHit]
```

## 6. Représentation interne

```python
# services/mcp.py
from dataclasses import dataclass

@dataclass(frozen=True)
class McpWorkspaceRef:
    name: str
    api_key: str


def normalize_refs(
    req: SingleWorkspaceRequest | MultiWorkspaceRequest,
) -> list[McpWorkspaceRef]:
    if isinstance(req, SingleWorkspaceRequest):
        return [McpWorkspaceRef(name=req.workspace, api_key=req.api_key)]
    return [McpWorkspaceRef(name=w.name, api_key=w.api_key) for w in req.workspaces]
```

## 7. Service search

```python
async def search(
    *,
    refs: list[McpWorkspaceRef],
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    secret_resolver: _ResolverProtocol,
) -> list[SearchHit]:
    tasks = [
        _search_one(
            ref=r, query=query, top_k=top_k, min_score=min_score,
            config_pool=config_pool, pool_registry=pool_registry,
            apikey_cache=apikey_cache, secret_resolver=secret_resolver,
        )
        for r in refs
    ]
    results = await asyncio.gather(*tasks)
    return [hit for ws_result in results for hit in ws_result.hits]


async def _search_one(
    *,
    ref: McpWorkspaceRef,
    query: str,
    top_k: int,
    min_score: float,
    config_pool: asyncpg.Pool,
    pool_registry: WorkspacePoolRegistry,
    apikey_cache: ApiKeyCache,
    secret_resolver: _ResolverProtocol,
) -> _WorkspaceResult:
    auth = await _authenticate(ref=ref, config_pool=config_pool, apikey_cache=apikey_cache)
    ctx = await _load_workspace_context(config_pool, ref.name)

    api_key: str | None = None
    if ctx["api_key_ref"]:
        api_key = secret_resolver.resolve_with_retry(_to_vault_ref(ctx["api_key_ref"]))

    provider = make_provider(
        provider=ctx["provider"], model=ctx["model"],
        api_key=api_key, base_url=ctx["base_url"],
    )
    query_vec = await provider.embed_query(query)

    ws_pool = await pool_registry.get_workspace_pool(ref.name, ctx["rag_cnx"])
    hits = await vector_search(
        ws_pool,
        query_vec=query_vec,
        top_k=top_k,
        min_score=min_score,
        workspace_name=ref.name,
        indexer_used=auth.indexer_used,
    )
    return _WorkspaceResult(
        workspace_name=ref.name,
        indexer_used=auth.indexer_used,
        hits=hits,
    )
```

### Auth helper (réutilise pattern M4b)

```python
async def _authenticate(
    *,
    ref: McpWorkspaceRef,
    config_pool: asyncpg.Pool,
    apikey_cache: ApiKeyCache,
) -> _CacheEntry:
    cached = apikey_cache.get(ref.name, ref.api_key)
    if cached is not None:
        return cached

    row = await config_pool.fetchrow(
        """
        SELECT w.id, w.api_key_hash,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        ref.name,
    )
    if row is None:
        raise WorkspaceNotFound(ref.name)

    if not verify_api_key(ref.api_key, row["api_key_hash"]):
        raise HTTPException(401, "invalid_workspace_apikey")

    entry = _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )
    apikey_cache.put(ref.name, ref.api_key, entry)
    return entry
```

**Pourquoi pas factoriser avec `require_workspace_apikey` (M4b)** : M4b prend un `Request` FastAPI et a une signature de dependency. M4c prend un `McpWorkspaceRef`. La factorisation propre exigerait d'extraire une fonction `_verify_workspace_apikey(name, api_key, pool, cache) -> _CacheEntry` partagée. Refacto reportée — pas dans le scope M4c.

## 8. SQL pgvector (`db/workspace_search.py`)

```python
from __future__ import annotations
import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from rag.schemas.mcp import SearchHit

log = structlog.get_logger(__name__)


async def vector_search(
    workspace_pool: asyncpg.Pool,
    *,
    query_vec: list[float],
    top_k: int,
    min_score: float,
    workspace_name: str,
    indexer_used: str,
) -> list[SearchHit]:
    """Top-k chunks avec score cosine >= min_score.

    Over-fetch top_k * 4 par ORDER BY distance (utilise l'index ivfflat),
    filtre min_score en Python, slice top_k.
    """
    async with workspace_pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            """
            SELECT path, chunk_index, content,
                   1 - (embedding <=> $1::vector) AS score
            FROM embeddings
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            query_vec,
            top_k * 4,
        )

    hits = [
        SearchHit(
            workspace=workspace_name,
            indexer=indexer_used,
            path=r["path"],
            chunk_index=r["chunk_index"],
            content=r["content"],
            score=float(r["score"]),
        )
        for r in rows
        if float(r["score"]) >= min_score
    ]
    return hits[:top_k]
```

## 9. Router

```python
# api/mcp.py
from __future__ import annotations
from fastapi import APIRouter, Request

from rag.schemas.mcp import McpRequest, McpResponse
from rag.services.mcp import normalize_refs, search


def build_mcp_router() -> APIRouter:
    router = APIRouter(tags=["mcp"])

    @router.post("/mcp", response_model=McpResponse)
    async def post_mcp(payload: McpRequest, request: Request) -> McpResponse:
        refs = normalize_refs(payload)
        hits = await search(
            refs=refs,
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score,
            config_pool=request.app.state.pools.config_pool,
            pool_registry=request.app.state.pools,
            apikey_cache=request.app.state.apikey_cache,
            secret_resolver=request.app.state.resolver,
        )
        return McpResponse(query=payload.query, results=hits)

    return router
```

## 10. Matrice d'erreurs

| Code | Détail | Source | Quand |
|---|---|---|---|
| **200** | `{query, results: [...]}` | router | succès (results peut être `[]`) |
| **401** | `invalid_workspace_apikey` | `_authenticate` | bcrypt verify fails sur ≥1 ref |
| **404** | `workspace_not_found` (name) | `_authenticate` | workspace inexistant ou pas d'indexer_config |
| **422** | _(Pydantic standard)_ | DTO | body invalide ou mix single+multi (extra forbid) |
| **502** | `embedding_provider_error` | handler (M4b T4) | provider HS / rate-limited / auth |
| **503** | `vault_unreachable` | handler M2 | Harpocrate indispo |
| **500** | _(handler générique)_ | handler | bug interne |

**Fail-fast asyncio.gather** : 1re exception cancel les autres tasks.
Le client reçoit l'erreur du 1er ref qui échoue (ordre d'exécution
non déterministe entre refs — accepté).

## 11. Tests

### Unit (sans DB, sans réseau)

- `tests/unit/schemas/test_mcp_dto.py` :
  - accept single (`{workspace, api_key, query}`)
  - accept multi (`{workspaces: [...], query}`)
  - reject mix (`{workspace, workspaces, query}`) — extra forbid
  - reject `top_k=0`, `top_k=51`
  - reject `min_score=2.0`, `min_score=-1.1`
  - reject `workspaces=[]`, `workspaces=[11+ items]`
  - reject `query=""`

- `tests/unit/services/test_mcp_normalize.py` :
  - `normalize_refs(SingleRequest)` → 1 ref avec name, api_key
  - `normalize_refs(MultiRequest)` → N refs préservant l'ordre

- `tests/unit/services/test_mcp_search.py` :
  - succès single : `_search_one` appelé 1×, result concat
  - succès multi : tasks gathered en parallèle, ordre concat = ordre refs
  - fail-fast `WorkspaceNotFound` : 1 ref ghost → propage 404
  - fail-fast `HTTPException(401)` : 1 ref bad_key → propage 401
  - cache hit : `pool.fetchrow` non appelé en auth pour le 2e ref

- `tests/unit/indexer/test_providers_embed_query.py` :
  - `OpenAIProvider.embed_query("hi")` → délègue, retourne `embed_texts([text])[0]`
  - `OpenAIProvider.embed_query` lève `EmbeddingProviderUnreachable` si embed_texts retourne `[]`
  - `VoyageProvider.embed_query("hi")` envoie `input_type="query"` (sniffé via httpx mock transport)
  - `OllamaProvider.embed_query("hi")` délègue

- `tests/unit/db/test_workspace_search.py` :
  - over-fetch et filtre testés par mock asyncpg : `fetch` reçoit `LIMIT top_k * 4`, le filtre Python keep `score >= min_score`, slice `top_k`.

### Integration (DB jetable LXC 303)

- `tests/api/test_mcp_single.py` :
  - crée workspace OpenAI (fake provider injecté), push 3 docs avec scores artificiels, `/mcp` single retourne top_k=2 chunks, scores corrects, ordre par score desc
  - `/mcp` avec `min_score=0.99` (très strict) → `results: []`, 200

- `tests/api/test_mcp_multi.py` :
  - 2 workspaces avec fake provider, push docs dans chaque
  - multi-request retourne items concat dans l'ordre des `workspaces`
  - chaque item porte le bon `workspace` et `indexer`

- `tests/api/test_mcp_errors.py` :
  - 422 body manquant
  - 422 mix `{workspace, workspaces}`
  - 422 `top_k=0`
  - 404 workspace inconnu
  - 401 bad api_key
  - 401 sur multi avec 1 mauvais (fail-fast)

### Smoke opt-in

- `tests/api/test_mcp_e2e_ollama_smoke.py` (`@pytest.mark.smoke`) :
  - workspace Ollama réel (`OLLAMA_TEST_URL`), push 2 docs, `/mcp` retourne le doc le plus pertinent avec score > 0.5.

## 12. Hors scope

- Cache du résultat `embed_query` inter-requête.
- Cache des `SearchHit` côté pgvector (re-query à chaque appel).
- Rate-limiting applicatif côté `/mcp`.
- Granularité scopes api_key (read-only vs write-only).
- Reranker post-cosine (cross-encoder).
- Hybrid search (BM25 + vector).
- Stream SSE des résultats.
- `errors[]` field en réponse (fail-fast assumé).
- Groupage explicite par indexer dans la réponse (chaque `SearchHit`
  porte son `indexer`, libre à l'agent de regrouper).

## 13. Risques connus

| Risque | Mitigation |
|---|---|
| api_keys dans access logs Caddy / Cloudflare | Documenter dans la PR : `log.json` à exclure de `/mcp` ou redact `api_key`/`workspaces[*].api_key` dans Caddyfile. |
| Embed_query dupliqué pour même indexer en multi-workspace | Accepté en M4c — 3 workspaces openai = 3 appels embed_query. Optimisation possible plus tard via groupage par indexer. |
| ivfflat approximation peut manquer des chunks à score élevé | Index ivfflat actuel utilise `lists=100` (défaut). Si recall insuffisant → tuning `SET ivfflat.probes` au niveau session. Pas dans M4c. |
| Cancellation `asyncio.gather` laisse des httpx clients ouverts | `httpx.AsyncClient` est utilisé en `async with` dans chaque provider → cleanup automatique sur CancelledError. |
| Master-key bypass via `/mcp` | Pas possible : `/mcp` ne lit pas le bearer header. Master key reste exclusivement pour admin. |
| Mix single+multi silencieux | `extra="forbid"` rejette les payloads qui mélangent les fields → 422 explicite. |
