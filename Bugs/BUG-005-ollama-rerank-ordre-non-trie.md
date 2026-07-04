# BUG-005 — Provider Ollama : résultats tronqués sans tri par score et top_n jamais envoyé

**Statut : 🔴 à corriger**

- **Zone** : backend / rerank
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/rerank/providers/ollama.py:43-72`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — tri défensif localisé

## Description

Contrairement aux 4 autres providers, le body Ollama omet tout paramètre `top_n`/`top_k`, et le traitement de la réponse ignore le `relevance_score` documenté, renvoyant `indices[:top_k]` dans l'ordre de réponse du serveur. Si l'endpoint renvoie les résultats dans l'ordre des documents d'entrée — courant pour les implémentations de serveurs rerank qui renvoient un score par doc — le code sélectionne les **k premiers** documents, pas les k plus pertinents, sans aucune erreur.

## Scénario de défaillance

1. Workspace configuré avec rerank ollama ; le serveur renvoie `results` dans l'ordre d'entrée avec des scores.
2. 50 hits pré-rerank, top_k=5 → les 5 hits retournés sont simplement les 5 premiers du classement **vectoriel** (ou les 5 premières entrées de la réponse) — le reranking est un no-op silencieux ou activement faux.

## Code concerné

```python
results = data.get("results", [])
indices = [int(r["index"]) for r in results]
return indices[:top_k]   # relevance_score ignoré, ordre du serveur aveuglément suivi
```

## Piste de correction

Trier `results` par `relevance_score` décroissant avant le slice (défensif, conforme au format de réponse documenté). Envoyer aussi `top_n` dans le body si supporté.
