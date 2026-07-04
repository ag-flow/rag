# BUG-053 — `delete_provider_key` référence la colonne supprimée `workspaces.api_key_ref`

**Statut : 🔴 à corriger**

- **Zone** : backend / services/provider_api_keys
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/provider_api_keys.py:174-177`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

La migration `033_workspace_api_keys.sql` exécute `ALTER TABLE workspaces DROP COLUMN IF EXISTS api_key_ref;`. Le contrôle de référence dans `delete_provider_key` interroge toujours cette colonne → `UndefinedColumnError`. Le contrôle voulu vise vraisemblablement `indexer_configs.api_key_ref` (et/ou `rerank_configs`, `workspace_llm_configs`).

## Scénario de défaillance

Toute suppression de clé API provider → 500. Feature cassée depuis la migration 033.

## Code concerné

```python
ref_count = await conn.fetchval(
    "SELECT count(*) FROM workspaces WHERE api_key_ref LIKE $1",
    f"%{row['harpo_path']}%",
)
```

## Piste de correction

Interroger `indexer_configs.api_key_ref` (plus les autres tables contenant des refs) au lieu de `workspaces`.
