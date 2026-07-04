# BUG-048 — La récupération au crash orpheline les lignes de payload push/delete et perd silencieusement les documents pushés

**Statut : 🟢 corrigé**

- **Zone** : backend / sync/recovery + sync/executor
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/sync/recovery.py:9-37`, `executor.py:371-378,508-515`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`reset_stale_running_jobs` marque les jobs `running` crashés en `error`. Les lignes de payload push/delete ne sont supprimées que dans le `finally` de l'executor ; les jobs tués par la récupération ne l'atteignent jamais, donc `push_job_payloads`/`delete_job_payloads` s'accumulent indéfiniment (pas de FK cascade sur le statut du job). De plus, contrairement aux sources git planifiées (qui obtiennent un nouveau job à l'intervalle suivant), un job push errored n'a aucun chemin de retry : l'API a accepté le document (style 202) mais il n'est jamais indexé.

## Scénario de défaillance

Le conteneur worker OOM en plein job push. Après redémarrage le job affiche `stale_at_boot` ; le document du client est silencieusement absent de l'index et sa ligne de payload fuit dans la config DB.

## Code concerné

```python
UPDATE index_jobs SET status='error', error_message='stale_at_boot', ...
WHERE status = 'running'   -- ligne de payload push survit, job jamais retenté
```

## Piste de correction

Dans la récupération, remettre les jobs push/delete en `pending` (idempotent — payload toujours présent, le hash-skip protège des doublons) au lieu de `error` ; purger les payloads pour les jobs terminaux.
