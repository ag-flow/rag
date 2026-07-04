# BUG-010 — `sync_worker_poll_interval_seconds` sans borne basse : 0/négatif = busy loop

**Statut : 🟢 corrigé**

- **Zone** : backend / config + sync worker
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/config.py:33`, `backend/src/rag/sync/worker.py:128`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — un `Field(ge=1)`

## Description

`sync_default_interval_seconds` est gardé avec `ge=60`, mais l'intervalle de poll voisin est un simple `int = 30`. Le worker l'utilise comme `asyncio.wait_for(..., timeout=self._poll_interval)` ; `timeout=0` (ou négatif) expire immédiatement, faisant tourner la boucle de poll (une requête DB par itération) à 100 % d'un cœur.

## Scénario de défaillance

1. Le `.env` contient `SYNC_WORKER_POLL_INTERVAL_SECONDS=0` (quelqu'un qui « désactive » le polling, ou une erreur de templating).
2. Settings valide sans broncher → le worker martèle les requêtes `index_jobs`/`workspace_sources` en boucle serrée, saturant CPU et Postgres.

## Code concerné

```python
sync_worker_poll_interval_seconds: int = 30   # pas de ge=1
sync_default_interval_seconds: int = Field(default=300, ge=60)  # le voisin, LUI, est gardé
```

## Piste de correction

`Field(default=30, ge=1)`.
