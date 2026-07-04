# BUG-049 — Reindex (changement d'indexeur) recrée `embeddings` sans les migrations workspace → schéma définitivement divergent

**Statut : 🔴 à corriger**

- **Zone** : backend / services/jobs + db
- **Sévérité** : **critique**
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/services/jobs.py:260-267`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — corruption de schéma, factorisation d'une fonction de provisioning partagée

## Description

`reindex_workspace` drop la table `embeddings` (`DROP TABLE IF EXISTS embeddings CASCADE`) et la recrée via `create_embeddings_table()`, qui ne crée que les colonnes de base (pas de `section_id`, `chunk_hash`, index partiel unique, `content_tsv` GENERATED + GIN). Il n'appelle jamais `apply_pending()`. Les migrations workspace 002/003 disparaissent — et ne peuvent **jamais** être réappliquées car `workspace_schema_migrations` dans cette DB enregistre toujours les versions 1-4, donc `apply_pending` est un no-op pour toujours. De plus, le CASCADE drop le FK mais laisse toutes les lignes `sections` orphelines, et le `UNIQUE(path, chunk_index)` recréé (droppé par la migration 002) entre en conflit avec le pipeline structuré.

## Scénario de défaillance

L'admin confirme un changement d'indexeur/modèle sur un workspace en `engine='structured'` ou recherche hybride. La prochaine indexation crashe avec `UndefinedColumnError: column "chunk_hash" does not exist` (upsert_structured) et toute recherche hybride/lexicale échoue sur `content_tsv`. Aucun restart ni run de migration ne corrige ; seulement du DDL manuel.

## Code concerné

```python
drop_conn = await asyncpg.connect(ws_dsn)
try:
    await drop_conn.execute("DROP TABLE IF EXISTS embeddings CASCADE")
finally:
    await drop_conn.close()
await create_embeddings_table(ws_dsn, dimension=new_dimension)   # pas d'apply_pending()
```

## Piste de correction

Après `create_embeddings_table`, réinitialiser `workspace_schema_migrations` (`DELETE FROM ...`) et appeler `apply_pending(ws_dsn)` ; truncate aussi `sections`. Mieux : factoriser une seule fonction « provision workspace schema » partagée avec `create_workspace`.
