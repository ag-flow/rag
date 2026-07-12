# BUG-058 — `WorkspacePoolRegistry.get_workspace_pool` : race check-then-create fuit des pools ; l'éviction LRU peut fermer un pool en usage actif

**Statut : 🟢 corrigé**

- **Zone** : backend / db/pool
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/db/pool.py:60-80`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — concurrence, refcounting/lock, subtil

## Description

(a) Aucun lock autour du check de cache et de `await asyncpg.create_pool(...)`. Deux requêtes concurrentes pour le même workspace ratent toutes deux le cache, créent toutes deux des pools ; la seconde écrase la première dans le dict → le premier pool (avec jusqu'à `max_size` connexions PG ouvertes) n'est jamais fermé. (b) L'éviction `await oldest_pool.close()` peut toucher un pool qu'une autre coroutine vient de recevoir de `get_workspace_pool` mais n'a pas encore `acquire()` → `InterfaceError: pool is closed` sur une requête vivante.

## Scénario de défaillance

Recherche MCP multi-workspaces (`asyncio.gather` sur `_search_one`) plus requêtes HTTP concurrentes sur cache froid → pools dupliqués fuient des connexions jusqu'à épuiser `max_connections` de Postgres ; avec >16 workspaces actifs, les évictions font aléatoirement 500 des recherches en cours.

## Code concerné

```python
if workspace_name in self._workspace_pools:
    ...
pool = await asyncpg.create_pool(dsn, ...)          # point d'interleaving
self._workspace_pools[workspace_name] = pool        # peut écraser une création concurrente
```

## Piste de correction

`asyncio.Lock` par clé (ou lock registre unique) autour du get-or-create ; pour l'éviction, utiliser du refcounting ou fermer async uniquement quand idle.
