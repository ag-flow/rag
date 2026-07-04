# BUG-002 — Les exceptions des providers rerank (429/timeout/auth) ne sont jamais capturées

**Statut : 🔴 à corriger**

- **Zone** : backend / rerank + services/mcp
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/rerank/protocol.py:6-19`, `backend/src/rag/services/mcp.py:351-365`, `backend/src/rag/api/errors.py` (aucun handler)
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — décision de design (fallback dégradé vs mapping HTTP), impact multi-fichiers

## Description

Une taxonomie d'exceptions complète existe (`RerankAuthError`, `RerankRateLimited`, `RerankProviderUnreachable`) mais aucun code hors de `rerank/` ne les capture. `register_error_handlers` ne mappe que les sous-classes `AdminError` (il existe `EmbeddingProviderUnavailable` pour les embeddings, rien pour le rerank). `search()` documente même « Fail-fast … Aucun résultat partiel » via `asyncio.gather` : l'échec du rerank d'un seul workspace tue aussi une recherche multi-workspaces. Aucun fallback vers les hits non rerankés.

## Scénario de défaillance

1. Cohere renvoie un 429 transitoire.
2. Chaque recherche MCP sur le workspace lève `RerankRateLimited` → non capturée → HTTP 500 générique au lieu d'un 429/503 ou de résultats dégradés (non rerankés).
3. Idem pour un timeout de 30 s : l'utilisateur attend 30 s puis reçoit un 500.

## Code concerné

```python
# services/mcp.py — aucun try/except autour de :
indices = await reranker.rerank(query=query, documents=documents, top_k=top_k)
```

## Piste de correction

Capturer `RerankProviderError` dans `_search_one` et soit retomber sur l'ordre vector/RRF avec un log d'avertissement, soit mapper la taxonomie vers des statuts HTTP corrects via un exception handler. Décider aussi du comportement en recherche multi-workspaces (partiel vs fail-fast).
