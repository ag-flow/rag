# BUG-038 — Les jobs git contournent entièrement la machinerie de retry/backoff et de circuit-breaker

**Statut : 🟢 corrigé**

- **Zone** : backend / sync/executor
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/sync/executor.py:595-603` (vs push/delete à `:337-370,475-507`)
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — cohérence de la gestion d'erreur transversale

## Description

Les jobs push et delete classifient les erreurs (`classify_indexer_error`) → les erreurs transitoires sont replanifiées avec backoff, les erreurs bloquantes ouvrent le circuit breaker du workspace. Les jobs git (`schedule`/`webhook`/`manual`) passent par le `except` générique de `execute_next_pending_job` : toute erreur — y compris `EmbeddingRateLimited` ou `EmbeddingAuthError` — est marquée terminale `error`, sans reschedule, sans ouverture de circuit.

## Scénario de défaillance

Une clé API expirée : chaque sync planifié clone/pull, chunke tout le changeset, appelle le provider, reçoit 401 → job error. Le circuit breaker ne s'ouvre jamais, donc le scheduler recrée un job à chaque intervalle, brûlant du travail git et CPU et martelant le provider à l'infini. Un 429 transitoire en cours de job tue de même tout le sync au lieu de faire du backoff.

## Code concerné

```python
except Exception as e:
    msg = _format_error(e)
    log.exception("sync.executor.job_error", job_id=str(job.job_id))
    await _mark_job_error(config_pool, job_id=job.job_id, error_message=msg)
```

## Piste de correction

Appliquer la même logique `classify_indexer_error` + `_reschedule_job`/`open_circuit` dans le chemin d'erreur des jobs git.
