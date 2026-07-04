# BUG-012 — Après rerank, `SearchHit.score` porte toujours le score pré-rerank : trier par score annule le reranking

**Statut : 🟢 corrigé**

- **Zone** : backend / services/mcp + schemas/mcp + protocole rerank
- **Sévérité** : basse
- **Complexité** : modérée
- **Confiance** : faible (partiellement assumé dans un commentaire du code)
- **Fichiers** : `backend/src/rag/services/mcp.py:364-365`, `backend/src/rag/schemas/mcp.py:57` (`rerank_score` toujours None)
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — extension du protocole `(index, score)` sur 5 providers + service + schéma

## Description

Les providers ne renvoient que des indices ; les scores de pertinence des API de rerank sont jetés. Les `hits` réordonnés gardent leur `score` vector/RRF : les `results` de la réponse sont ordonnés par rerank mais le champ `score` est non monotone et incohérent avec cet ordre ; `DebugTrace.rerank_score` est documenté mais ne peut jamais être peuplé avec le protocole `list[int]` actuel.

## Scénario de défaillance

1. Un client MCP (ou l'UI playground) trie/filtre les résultats par `score` — pratique standard — et revient de fait à l'ordre pré-rerank, ou écarte le meilleur choix du reranker parce que son score cosinus est sous un seuil côté client.
2. En recherche multi-workspaces, les listes concaténées par workspace rendent la comparaison de scores inter-workspaces doublement trompeuse.

## Code concerné

```python
rerank_score: float | None = None  # null jusqu'à ce que le reranker expose les scores
...
async def rerank(...) -> list[int]:   # les scores sont structurellement jetés
```

## Piste de correction

Étendre le protocole pour renvoyer des paires `(index, relevance_score)` et peupler `rerank_score` / écraser `score`, ou documenter que `score` est pré-rerank.
