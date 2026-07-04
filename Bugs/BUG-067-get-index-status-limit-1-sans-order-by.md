# BUG-067 — `get_index_status` : `workspace_sources ... LIMIT 1` sans ORDER BY

**Statut : 🔴 à corriger**

- **Zone** : backend / db/mcp_tools
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/db/mcp_tools.py:23-27`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Avec plusieurs sources par workspace, les `last_indexed_at`/`next_sync_at` renvoyés viennent d'une source arbitraire (dépendante du plan), donc le bloc de santé « sync » est non déterministe.

## Scénario de défaillance

Workspace avec 2 sources ; l'endpoint de statut alterne entre la source périmée et la fraîche d'un appel à l'autre.

## Code concerné

```sql
SELECT last_indexed_at, next_sync_at FROM workspace_sources WHERE workspace_id = $1 LIMIT 1
```

## Piste de correction

Agréger (`MAX(last_indexed_at)`, `MIN(next_sync_at)`) ou `ORDER BY` explicite.
