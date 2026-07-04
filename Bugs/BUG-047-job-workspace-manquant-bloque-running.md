# BUG-047 — Un job pické avec contexte workspace manquant reste bloqué en `running`

**Statut : 🟢 corrigé**

- **Zone** : backend / sync/executor
- **Sévérité** : basse
- **Complexité** : simple
- **Confiance** : faible (nécessite la disparition de la ligne workspace entre création FK et pick)
- **Fichiers** : `backend/src/rag/sync/executor.py:98-100`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`pick_next_pending_job` fait passer le job en `running` dans la transaction, puis renvoie `None` si la requête de contexte ne trouve aucune ligne workspace. Le job reste `running` pour toujours (jusqu'à la récupération au boot), et le garde `NOT EXISTS (status IN pending,running)` du scheduler bloque tout nouveau job pour cette source.

## Scénario de défaillance

Un chemin de suppression de workspace qui ne cascade pas les jobs (ou une migration partiellement appliquée) laisse un job référençant un workspace manquant : le sync de la source s'arrête silencieusement jusqu'au redémarrage du service.

## Code concerné

```python
if context is None:
    log.error("sync.picker.workspace_not_found", ...)
    return None   # job déjà UPDATE en 'running', jamais finalisé
```

## Piste de correction

Marquer le job `error` avant de renvoyer `None` dans la branche `context is None`.
