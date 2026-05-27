# M8 — Reranking backend

> **Statut** : design validé pour implémentation.
> **Spec produit ciblée** : `specs/09-roadmap.md` § Reranking.
> **Prérequis** : M4c (MCP search multi-workspace), M5c (Harpocrate vaults), M5e (api_key chiffrée), M5f (préfixe `/api/admin`).

## 1. Contexte et motivation

Le MCP search actuel (`backend/src/rag/services/mcp.py`) effectue : embed query → `vector_search` top_k (pgvector cosine) → retourne les hits. La qualité dépend uniquement de la similarité cosinus dans l'espace d'embedding, qui est rapide mais peu discriminant sur les variantes proches.

Le **reranking** ajoute une seconde passe après pgvector : on récupère plus de candidats (`top_k_pre_rerank`, default 50), puis un modèle dédié (Cohere Rerank / Voyage Rerank / BGE-Ollama) trie ces candidats par pertinence cross-encoder (modèle qui voit query + document ensemble, plus précis que dual-encoder embedding).

Ce jalon livre l'infrastructure backend : config par workspace, providers, intégration dans le flow MCP. **Le frontend dédié (onglet Rerank dans WorkspaceDetailPanel) est hors-scope M8** — jalon M8b à venir.

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Config **par workspace** (table dédiée `rerank_configs`) | Flexibilité : chaque workspace peut activer/désactiver et choisir son provider |
| D2 | Rerank **per-workspace avant merge** dans `search()` | Seul cohérent avec D1 — config globale aurait conflit si workspaces ont rerankers différents |
| D3 | 3 providers : **Cohere, Voyage, Ollama** | Couvre la roadmap |
| D4 | **Fail-fast** sur défaillance du reranker (timeout / 5xx / 4xx) | Cohérent avec `mcp.py:171` pattern existant. Pas de fallback silencieux à pgvector seul — on ne ment jamais sur la qualité |
| D5 | **Opt-in** : pas de row dans `rerank_configs` → comportement actuel (pas de rerank) | Backward compat avec workspaces existants |
| D6 | `top_k_pre_rerank` configurable par workspace (default 50) | Pool de candidats tunable par corpus |
| D7 | `api_key_ref` = référence Harpocrate (pas le secret en clair) | Pattern aligné avec `indexer_configs` et `harpocrate_vaults` |
| D8 | Validation **eager** de `api_key_ref` au PUT | Symétrique à `indexer_configs._validate_ref_via_vault` |
| D9 | Table dédiée (pas JSONB sur `workspaces`) | Type-safe, contraintes SQL, requêtable |
| D10 | `workspace_id` PRIMARY KEY (pas d'`id` séparé) | 1-to-1 strict avec workspaces |
| D11 | Pas de registry `rerank_model_dimensions` | Pas de dimension fixe à matérialiser (contrairement aux embeddings) |
| D12 | Skip du rerank si `len(hits) ≤ 1` | Sans intérêt et coûteux pour un singleton |

## 3. Schéma BDD

### 3.1 Migration `011_rerank_configs.sql`

```sql
-- Migration 011 — rerank_configs : config rerank par workspace (opt-in)
--
-- Workspace SANS row dans cette table → pas de rerank (comportement par défaut).
-- Cascade ON DELETE : suppression workspace → suppression rerank_config auto.

CREATE TABLE rerank_configs (
    workspace_id        UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    base_url            TEXT,
    api_key_ref         TEXT,
    top_k_pre_rerank    INT NOT NULL DEFAULT 50 CHECK (top_k_pre_rerank > 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 3.2 Invariants

- 1 row max par workspace (PRIMARY KEY).
- `provider ∈ {cohere, voyage, ollama}` — validé Pydantic à l'API admin + au lookup factory.
- `top_k_pre_rerank > 0` (CHECK SQL).
- À l'exécution, si `top_k > top_k_pre_rerank`, on prend `max(top_k, top_k_pre_rerank)` côté `vector_search` puis on garde les top_k post-rerank.
- `ON DELETE CASCADE` : si workspace supprimé → rerank_config supprimée auto.

## 4. Architecture providers

### 4.1 Modules backend

```
backend/src/rag/rerank/
├── __init__.py
├── protocol.py            → RerankProvider Protocol + exceptions
└── providers/
    ├── __init__.py
    ├── factory.py         → make_rerank_provider()
    ├── cohere.py          → CohereRerankProvider
    ├── voyage.py          → VoyageRerankProvider
    └── ollama.py          → OllamaRerankProvider
```

Parallèle direct de `backend/src/rag/indexer/providers/` (M4a).

### 4.2 Protocol `RerankProvider`

```python
# backend/src/rag/rerank/protocol.py
from __future__ import annotations
from typing import Protocol


class RerankProviderError(RuntimeError):
    """Base : toute erreur reranker."""


class RerankAuthError(RerankProviderError):
    """401/403 du provider."""


class RerankRateLimited(RerankProviderError):
    """429 du provider."""


class RerankProviderUnreachable(RerankProviderError):
    """Timeout / connection refused / 5xx."""


class RerankProvider(Protocol):
    async def rerank(
        self, *, query: str, documents: list[str], top_k: int,
    ) -> list[int]:
        """Retourne les indices des `top_k` documents les plus pertinents,
        triés par pertinence décroissante.

        - `len(retour) ≤ min(top_k, len(documents))`.
        - Indices ∈ `range(len(documents))`.
        - Lève `RerankAuthError` / `RerankRateLimited` / `RerankProviderUnreachable`.
        """
        ...
```

### 4.3 Implémentations HTTP (httpx.AsyncClient)

**Cohere** (POST `https://api.cohere.com/v2/rerank`) :
- Headers : `Authorization: Bearer <api_key>`, `Content-Type: application/json`.
- Body : `{"model": <model>, "query": <query>, "documents": <list[str]>, "top_n": <top_k>}`.
- Réponse : `{"results": [{"index": int, "relevance_score": float}, ...]}` (déjà trié).
- Extract `[r["index"] for r in results]`.

**Voyage** (POST `https://api.voyageai.com/v1/rerank`) :
- Headers : `Authorization: Bearer <api_key>`.
- Body : `{"query": ..., "documents": ..., "model": ..., "top_k": ...}`.
- Réponse : `{"data": [{"index", "relevance_score"}, ...]}` (déjà trié).

**Ollama** (POST `{base_url}/api/rerank`) :
- Pas d'auth.
- Body : `{"model": ..., "query": ..., "documents": [...]}`.
- Réponse (Ollama ≥ 0.4, doc référence Ollama API) : `{"results": [{"index": int, "relevance_score": float}, ...]}` — adapter le parser au runtime si la doc Ollama évolue. Le test unit `tests/unit/rerank/test_ollama.py` mocke ce format de référence ; tout drift sera détecté empiriquement à l'intégration E2E (T10).

Tous : timeout 30s, mapping erreurs HTTP → exceptions :
- 401/403 → `RerankAuthError`
- 429 → `RerankRateLimited`
- 5xx / `httpx.TimeoutException` / `httpx.ConnectError` → `RerankProviderUnreachable`

### 4.4 Factory

```python
def make_rerank_provider(
    *, provider: str, model: str,
    api_key: str | None, base_url: str | None,
) -> RerankProvider:
    if provider == "cohere":
        if not api_key:
            raise ValueError("cohere requires api_key")
        return CohereRerankProvider(model=model, api_key=api_key)
    if provider == "voyage":
        if not api_key:
            raise ValueError("voyage requires api_key")
        return VoyageRerankProvider(model=model, api_key=api_key)
    if provider == "ollama":
        if not base_url:
            raise ValueError("ollama requires base_url")
        return OllamaRerankProvider(model=model, base_url=base_url)
    raise ValueError(f"unknown rerank provider: {provider}")
```

## 5. Intégration flow MCP

### 5.1 Modification `_load_workspace_context` (services/mcp.py)

Ajouter un `LEFT JOIN rerank_configs` à la requête de chargement contexte :

```sql
SELECT
    ic.provider AS indexer_provider, ic.model AS indexer_model,
    ic.api_key_ref AS indexer_api_key_ref, ic.base_url AS indexer_base_url,
    w.rag_cnx,
    rc.provider AS rerank_provider, rc.model AS rerank_model,
    rc.api_key_ref AS rerank_api_key_ref, rc.base_url AS rerank_base_url,
    rc.top_k_pre_rerank
FROM workspaces w
JOIN indexer_configs ic ON ic.workspace_id = w.id
LEFT JOIN rerank_configs rc ON rc.workspace_id = w.id
WHERE w.name = $1
```

Si `rc.*` tous `NULL` → pas de rerank, sinon retourner aussi un dict `rerank = {provider, model, api_key_ref, base_url, top_k_pre_rerank}`.

### 5.2 Extension `_search_one()`

```python
# Schéma (pseudo-code, code complet dans le plan TDD) :
async def _search_one(...):
    auth = await _authenticate(...)
    ctx = await _load_workspace_context(...)        # +charge rerank si existe

    # Embedding (inchangé)
    api_key = await secret_resolver.resolve_with_retry(...) if ctx["indexer_api_key_ref"] else None
    provider = provider_factory(
        provider=ctx["indexer_provider"], model=ctx["indexer_model"],
        api_key=api_key, base_url=ctx["indexer_base_url"],
    )
    query_vec = await provider.embed_query(query)

    # Vector search avec pool potentiellement augmenté pour rerank
    rerank_cfg = ctx.get("rerank")
    pre_top_k = max(top_k, rerank_cfg["top_k_pre_rerank"]) if rerank_cfg else top_k
    ws_pool = await pool_registry.get_workspace_pool(ref.name, ctx["rag_cnx"])
    hits = await vector_search(ws_pool, query_vec=query_vec, top_k=pre_top_k, min_score=min_score, ...)

    # Rerank si configuré et > 1 hit
    if rerank_cfg and len(hits) > 1:
        rerank_api_key = None
        if rerank_cfg["api_key_ref"]:
            rerank_api_key = await secret_resolver.resolve_with_retry(
                _to_vault_ref(rerank_cfg["api_key_ref"], default_vault_name)
            )
        reranker = rerank_factory(
            provider=rerank_cfg["provider"], model=rerank_cfg["model"],
            api_key=rerank_api_key, base_url=rerank_cfg["base_url"],
        )
        documents = [h.content for h in hits]
        indices = await reranker.rerank(query=query, documents=documents, top_k=top_k)
        hits = [hits[i] for i in indices]
        log.info("mcp.rerank.applied", workspace=ref.name, pre_hits=len(documents), post_hits=len(hits))
    elif rerank_cfg:
        log.debug("mcp.rerank.skipped_singleton_or_empty", workspace=ref.name, hits=len(hits))

    return _WorkspaceResult(hits=hits[:top_k])
```

**Points clés** :
- Le rerank est appliqué **per-workspace, avant merge** (cohérent avec D2).
- Skip si `len(hits) ≤ 1` (D12).
- Exception du provider rerank → propagation → `asyncio.gather` lève → 502/503 client (fail-fast D4).
- Le `vector_search` retourne déjà `content` dans chaque hit (déjà chargé pour le RAG output).

### 5.3 Le `provider_factory` rerank

Comme pour les embeddings, exposer un `rerank_factory` paramétrable pour permettre monkey-patching en tests d'intégration :

```python
# Signature étendue de `search()` et `_search_one()` :
async def search(
    *,
    ...,
    provider_factory: Callable[..., EmbeddingProvider] | None = None,
    rerank_factory: Callable[..., RerankProvider] | None = None,
) -> list[SearchHit]:
    ...
    rerank_make = rerank_factory if rerank_factory is not None else make_rerank_provider
    ...
```

## 6. API admin

### 6.1 Endpoints sous `/api/admin/workspaces/{name}/rerank`

| Méthode | Body | Réponse |
|---|---|---|
| `GET` | — | 200 `RerankConfigResponse` ou 404 `rerank_not_configured` ou 404 `workspace_not_found` |
| `PUT` | `RerankSpec` | 200 `RerankConfigResponse` (upsert idempotent) |
| `DELETE` | — | 204 (idempotent : pas d'erreur si absent) |

Auth : `require_master_key_or_oidc_role("rag-admin")` (hérité du router admin).

### 6.2 Schémas Pydantic

```python
# backend/src/rag/schemas/admin.py — ajouts

class RerankSpec(BaseModel):
    """Body PUT /workspaces/{name}/rerank."""
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: Literal["cohere", "voyage", "ollama"]
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None
    top_k_pre_rerank: int = Field(default=50, gt=0, le=500)


class RerankConfigResponse(BaseModel):
    """Réponse GET / PUT /workspaces/{name}/rerank."""
    workspace_id: UUID
    provider: str
    model: str
    api_key_ref: str | None
    base_url: str | None
    top_k_pre_rerank: int
    created_at: str
    updated_at: str
```

**`WorkspaceResponse` inchangé** : pas d'exposition de rerank dans le GET workspace global pour éviter le coupling. Le frontend devra appeler `GET /rerank` séparément (jalon M8b).

### 6.3 Service `rerank_configs`

```python
# backend/src/rag/services/rerank_configs.py — nouveau fichier

async def get_rerank_config(
    workspace_id: UUID, config_pool: asyncpg.Pool,
) -> dict | None:
    """Retourne la config rerank ou None si absente."""

async def upsert_rerank_config(
    *, workspace_id: UUID, spec: RerankSpec,
    config_pool: asyncpg.Pool,
    resolver: _ResolverProtocol, default_vault_name: str,
) -> dict:
    """Upsert ON CONFLICT workspace_id DO UPDATE.
    Validation eager api_key_ref via Harpocrate (D8) si défini.
    """

async def delete_rerank_config(
    workspace_id: UUID, config_pool: asyncpg.Pool,
) -> None:
    """Idempotent : pas d'erreur si la config n'existe pas."""
```

### 6.4 Codes erreur

- 404 `workspace_not_found` : si le `name` n'existe pas (avant 404 rerank).
- 404 `rerank_not_configured` : workspace existe mais pas de config rerank.
- 422 sur PUT : api_key_ref invalide (eager validation Harpocrate échoue).
- 503 sur PUT : Harpocrate down au moment de la validation eager.

## 7. Tests

| Niveau | Fichier | Couverture |
|---|---|---|
| Unit providers | `tests/unit/rerank/test_cohere.py`<br>`tests/unit/rerank/test_voyage.py`<br>`tests/unit/rerank/test_ollama.py` | Mock httpx : parse OK, 401→AuthError, 429→RateLimited, 5xx+timeout→Unreachable |
| Unit factory | `tests/unit/rerank/test_factory.py` | 3 providers OK + unknown + missing api_key/base_url |
| Integration migration | `tests/integration/test_migration_011_rerank_configs.py` | Schéma, FK CASCADE, CHECK contrainte |
| Integration service | `tests/integration/test_services_rerank_configs.py` | get/upsert/delete + eager validation via mock resolver |
| Integration MCP avec rerank | `tests/integration/test_mcp_with_rerank.py` | E2E : workspace avec rerank → ordre changé, sans → inchangé, singleton → skip |
| Integration API admin | `tests/api/test_admin_workspaces_rerank.py` | GET 200/404, PUT upsert, DELETE 204 idempotent, 422 ref invalide |
| Integration fail-fast | `tests/integration/test_mcp_rerank_fail_fast.py` | Mock provider qui lève `RerankProviderUnreachable` → search propage |

## 8. Plan d'attaque (taille indicative)

11 tâches, ~2.5 jours backend.

| # | Tâche | Périmètre |
|---|---|---|
| T1 | Migration 011 + schemas Pydantic | Table SQL + `RerankSpec` + `RerankConfigResponse` |
| T2 | Protocol `RerankProvider` + exceptions | `protocol.py` + hiérarchie exceptions |
| T3 | Provider Cohere + tests unit | httpx mock, 4 cas erreur + 1 OK |
| T4 | Provider Voyage + tests unit | idem |
| T5 | Provider Ollama + tests unit | idem |
| T6 | Factory `make_rerank_provider` + tests | 3 providers + errors |
| T7 | Service `rerank_configs` (get/upsert/delete) + tests intégration | Eager validation Harpocrate, ON CONFLICT |
| T8 | Endpoints admin (GET/PUT/DELETE /rerank) + tests API | 3 endpoints + `RerankConfigResponse` |
| T9 | Intégration `_load_workspace_context` + `_search_one` | LEFT JOIN rerank, appel reranker conditionnel, `rerank_factory` injectable |
| T10 | Tests E2E MCP avec rerank + fail-fast | Workspace avec rerank → ordre changé, sans → inchangé, fail-fast |
| T11 | Doc roadmap + `.env.example` | Marquer M8 livré, doc ENV `COHERE_RERANK_*` / `VOYAGE_RERANK_*` |

## 9. Hors-scope explicite

- **Frontend Rerank** (onglet dans WorkspaceDetailPanel) → jalon **M8b**, ~0.5j.
- **Cache de résultats rerank** (mêmes query+docs → même ordre) → optimisation V2.
- **Métriques observabilité** dédiées rerank (latence, taux 5xx) → couvert par logs structlog, dashboards Grafana à part si besoin.
- **Mode "auto-model"** (laisser le provider choisir) → non, `model` toujours explicite.
- **Rerank multi-workspace après merge** → incompatible avec D1 (config par workspace).
- **Fallback à pgvector sans rerank si provider down** → exclu par D4 (fail-fast).
