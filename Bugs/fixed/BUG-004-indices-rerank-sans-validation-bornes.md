# BUG-004 — Indices renvoyés par le reranker appliqués sans validation de bornes ni d'unicité

**Statut : 🟢 corrigé**

- **Zone** : backend / rerank + services/mcp
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/mcp.py:364-365` ; tous les providers (`cohere.py:72`, `voyage.py:72`, `jina.py:75`, `ollama.py:71`, `dashscope.py:92`)
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — validation défensive centralisée, mécanique

## Description

Le protocole `RerankProvider` promet des indices dans `range(len(documents))`, mais aucun provider ne le vérifie — tous font `[int(r["index"]) for r in results]` directement depuis le JSON. `_search_one` fait ensuite `hits = [hits[i] for i in indices]`. Un indice hors bornes → `IndexError` → 500 ; un indice négatif (ex. `-1` d'un reranker self-hosted bugué) renvoie silencieusement le **dernier** hit ; des indices dupliqués dupliquent silencieusement des hits.

## Scénario de défaillance

1. Un endpoint rerank-compatible self-hosted (ou un changement d'API) renvoie `{"results":[{"index": 50, ...}]}` pour 20 documents → `hits[50]` → IndexError → 500 non géré.
2. Avec `index: -1` : mauvais document renvoyé, sans aucune erreur.

## Code concerné

```python
indices = await reranker.rerank(query=query, documents=documents, top_k=top_k)
hits = [hits[i] for i in indices]   # aucun contrôle de bornes
```

## Piste de correction

Valider `0 <= i < len(documents)` et dédupliquer dans chaque provider (ou de façon centralisée dans `_search_one`), en levant `RerankProviderUnreachable` / en loggant en cas de violation.
