# BUG-063 — `JobLogBus` : les buffers ne sont jamais libérés → croissance mémoire non bornée

**Statut : 🔴 à corriger**

- **Zone** : backend / services/job_log_bus
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/job_log_bus.py:19-55`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`publish`/`complete` append dans `self._buffers[job_id]` (max 500 events chacun) et `complete` ajoute à `self._done`, mais rien ne retire jamais les jobs finis de `_buffers`/`_done`. Chaque job sync/push/reindex retient en permanence jusqu'à 500 dicts de log en mémoire process.

## Scénario de défaillance

Un workspace sur un planning de sync à 5 minutes génère ~288 jobs/jour ; après des semaines d'uptime le process retient des centaines de milliers de dicts d'events de log → croissance régulière du RSS jusqu'à l'OOM.

## Code concerné

```python
buf = self._buffers.setdefault(job_id, [])
...
self._done.add(job_id)     # _buffers[job_id] retenu pour toujours
```

## Piste de correction

Évincer buffer + flag done après complétion (TTL différé pour laisser les subscribers tardifs), ou plafonner le nombre de jobs retenus (LRU).
