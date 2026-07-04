# BUG-020 — Auth push/delete workspace interroge des colonnes supprimées par la migration 033 : endpoints toujours en 500

**Statut : 🔴 à corriger**

- **Zone** : backend / auth + api/workspace
- **Sévérité** : **critique**
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/auth/workspace_auth.py:76-87`, utilisé par `backend/src/rag/api/workspace.py:22,60`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — réécriture d'une requête sur le modèle de `services/mcp.py:_authenticate`

## Description

`require_workspace_apikey` sélectionne `w.api_key_ref` et filtre sur `w.api_key_fingerprint` de la table `workspaces`. La migration `backend/migrations/033_workspace_api_keys.sql` **supprime** ces deux colonnes (`ALTER TABLE workspaces DROP COLUMN IF EXISTS api_key_fingerprint; ... DROP COLUMN IF EXISTS api_key_ref;`) et déplace les clés vers la table `workspace_api_keys` (que `services/mcp.py` et `mcp_standard.py` utilisent correctement). Aucune migration ultérieure ne les recrée.

## Scénario de défaillance

Tout `POST /workspaces/{name}/index` ou `DELETE /workspaces/{name}/index/{path}` avec une clé Bearer valide → asyncpg `UndefinedColumnError` → 500. **L'API de push est entièrement cassée** sur une base à la migration ≥ 033.

## Code concerné

```python
row = await pool.fetchrow(
    """
    SELECT w.id, w.api_key_ref, ...
    FROM workspaces w
    JOIN indexer_configs ic ON ic.workspace_id = w.id
    WHERE w.name = $1 AND w.api_key_fingerprint = $2
    """, name, fingerprint)
```

## Piste de correction

Réécrire la requête contre `workspace_api_keys` (filtres fingerprint + revoked_at/rotated_at), comme `services/mcp.py:_authenticate`.
