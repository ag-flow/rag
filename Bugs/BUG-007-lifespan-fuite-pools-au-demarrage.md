# BUG-007 — Échec du lifespan au démarrage : les pools Postgres fuient (cleanup uniquement autour du yield)

**Statut : 🔴 à corriger**

- **Zone** : backend / main.py (lifespan)
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/main.py:127-233`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — try/except ou AsyncExitStack, localisé

## Description

`registry.start()` ouvre les pools config + admin à la ligne 127. Tout ce qui peut lever ensuite — `run_migrations` (132), le boot guard `RuntimeError` (incohérence vault/workspace), `apply_pending_for_all_workspaces` (152, fail-fast documenté), la construction du resolver/vault, `sync_worker.start()` — se produit **avant** le `yield` (228), alors que le bloc `finally` (229-233) ne s'exécute que si le `yield` a été atteint. En cas d'échec au démarrage, `registry.close_all()` n'est jamais appelé.

## Scénario de défaillance

1. Une base workspace est injoignable au boot → `apply_pending_for_all_workspaces` lève → le service refuse de démarrer (voulu), mais les pools config/admin restent ouverts jusqu'à la mort du process.
2. Dans la suite de tests (`build_app` répété avec échecs de démarrage induits), fuite de connexions pouvant épuiser `max_connections` de Postgres ; avec un superviseur qui redémarre en boucle un conteneur en crash-loop, les connexions fuitées traînent jusqu'au teardown TCP.

## Code concerné

```python
await registry.start()
...
await run_migrations(registry.config_pool, target_dir)   # peut lever
...
try:
    yield
finally:
    ...
    await registry.close_all()   # sauté en cas d'échec au démarrage
```

## Piste de correction

Envelopper la section de démarrage dans un `try/except` qui ferme le registry (et arrête le worker s'il a démarré) avant de re-lever, ou utiliser `contextlib.AsyncExitStack`.
