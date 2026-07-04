# BUG-006 — L'endpoint `/api/rerank` n'existe pas dans Ollama upstream : le provider ne peut jamais fonctionner contre un Ollama standard

**Statut : 🔴 à corriger**

- **Zone** : backend / rerank
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Confiance** : faible (à vérifier contre la version d'Ollama réellement déployée)
- **Fichiers** : `backend/src/rag/rerank/providers/ollama.py:20-43`
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — nécessite investigation (versions/forks d'Ollama) et décision produit (retirer, gater, documenter)

## Description

La docstring affirme « Reranker Ollama local (depuis Ollama 0.4+) », mais Ollama upstream n'a jamais livré d'endpoint natif `/api/rerank` (feature request ouverte de longue date) ; seuls des forks/serveurs tiers l'exposent. Contre un Ollama standard, le POST renvoie 404 → branche `>= 400` → `RerankProviderUnreachable` à chaque recherche.

## Scénario de défaillance

1. Un admin pointe la config rerank d'un workspace vers son instance Ollama fonctionnelle (qui sert très bien les embeddings).
2. Chaque recherche rerankée échoue avec `ollama unexpected 404`.
3. Combiné au BUG-002 (exceptions non capturées), toutes les recherches renvoient 500.

## Code concerné

```python
url = f"{self._base_url}/api/rerank"
```

## Piste de correction

Vérifier contre la version d'Ollama effectivement déployée ; si non supporté, retirer/gater le provider ou documenter le fork requis ; ajouter une sonde de connectivité au moment de la config.
