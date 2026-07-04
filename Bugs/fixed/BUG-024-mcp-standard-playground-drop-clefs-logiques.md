# BUG-024 — `mcp_standard.rag_search` et playground droppent silencieusement les refs de clé logique → appels embedding non authentifiés

**Statut : 🟢 corrigé**

- **Zone** : backend / api/mcp_standard + api/playground
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/api/mcp_standard.py:83-84`, `backend/src/rag/api/playground.py:112-115,157-158`
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — helper partagé de normalisation de ref sur 4 sites (voir note transversale)

## Description

L'inverse du BUG-022 : ces sites ne résolvent la clé indexer que `if is_vault_ref(ref)` ; une ref de clé logique (format legacy, explicitement supporté par `RealIndexer` via wrapping default-vault) donne `api_key=None`.

## Scénario de défaillance

Workspace avec `api_key_ref="openai_embedding_key"` (forme logique) s'indexe très bien via le worker, mais MCP `rag_search` / chat playground construit le provider d'embedding avec `api_key=None` → 401 du provider → erreur de tool/500, de façon incohérente avec l'indexation.

## Code concerné

```python
if ctx.indexer_api_key_ref and is_vault_ref(ctx.indexer_api_key_ref):
    api_key = await ctx.resolver.resolve_with_retry(ctx.indexer_api_key_ref)
```

## Piste de correction

**Note transversale** : les BUG-022 et BUG-024 sont les deux faces de la même incohérence — 4 sites d'appel (`services/mcp.py`, `api/mcp_standard.py`, `api/playground.py`, `indexer/real.py`) normalisent chacun `indexer_configs.api_key_ref` différemment ; seul `RealIndexer` gère les deux formats stockés. Extraire **un** helper partagé (`is_vault_ref` sinon wrapper avec le vault par défaut) et l'utiliser dans les 4 sites corrige 022 et 024 ensemble.
