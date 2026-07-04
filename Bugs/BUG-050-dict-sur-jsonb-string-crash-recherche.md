# BUG-050 — `dict()` sur une string jsonb : le mapping des résultats de recherche crashe (asyncpg renvoie jsonb en `str`)

**Statut : 🔴 à corriger**

- **Zone** : backend / db (search + mcp_tools)
- **Sévérité** : **critique**
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/db/workspace_search.py:139,294`, `backend/src/rag/db/mcp_tools.py:132-136,172`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`) — enregistrer un codec jsonb au niveau du pool

## Description

Aucun `set_type_codec` pour json/jsonb n'est enregistré (vérifié sur tous les sites `create_pool` ; `register_vector` n'enregistre que le type `vector`). asyncpg renvoie donc les colonnes `jsonb` en `str`. `_fetch_vector_children`/`lexical_search` font `dict(r["metadata"])`, et `search_files_in_workspace`/`reconstruct_document` font `dict(r["metadata"]).get(...)`. `dict("...")` lève `ValueError`. Comme `embeddings.metadata` est `NOT NULL DEFAULT '{}'` (string truthy `"{}"`), chaque vraie ligne le déclenche. D'autres modules du même repo (`index_keys.py:64-65`, `sources.py:204`) font défensivement `isinstance(metadata, str) → json.loads`, confirmant le comportement str ; le module de recherche non. Les tests unitaires ne passent que parce qu'ils injectent des dicts pré-parsés via des pools mockés.

## Scénario de défaillance

Toute recherche MCP vector/hybride ou `search_files` contre une vraie DB workspace renvoyant ≥1 ligne → `ValueError` → HTTP 500.

## Code concerné

```python
metadata=dict(r["metadata"]) if r["metadata"] else None,   # r["metadata"] est une str comme '{"k":"v"}'
```

## Piste de correction

Enregistrer un codec jsonb (`json.loads`/`json.dumps`) via le `init=` du pool dans `WorkspacePoolRegistry`, ou appliquer la même normalisation `isinstance(str) → json.loads` que dans `index_keys.py`.
