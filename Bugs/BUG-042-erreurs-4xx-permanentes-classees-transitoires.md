# BUG-042 — Les erreurs HTTP 4xx permanentes du provider sont classées transitoires

**Statut : 🔴 à corriger**

- **Zone** : backend / indexer/providers + sync/error_classifier
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/indexer/providers/adapter.py:118-121`, `backend/src/rag/sync/error_classifier.py:16`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Tout statut inattendu (400 input invalide/trop long, 404 mauvais modèle, 413, 422) lève `EmbeddingProviderUnreachable`, que `classify_indexer_error` mappe en `transient` → les jobs push/delete retentent avec backoff exponentiel jusqu'à ~9 tentatives, puis ouvrent le *circuit breaker* avec une cause trompeuse « unreachable », bloquant tout le workspace.

## Scénario de défaillance

Un nom de modèle typo dans `indexer_configs` (404 du provider) : chaque job push retente pendant des heures (backoff 30s→7680s), puis ouvre le circuit du workspace comme si le provider était down ; la vraie cause (mauvaise config) est masquée en « Unexpected HTTP 404 (unreachable) ».

## Code concerné

```python
raise EmbeddingProviderUnreachable(f"Unexpected HTTP {response.status_code}")
# classifier : _TRANSIENT = (EmbeddingRateLimited, EmbeddingProviderUnreachable)
```

## Piste de correction

Ajouter un `EmbeddingBadRequest` distinct (4xx autres que 401/402/403/429) mappé en `permanent` dans le classifier.
