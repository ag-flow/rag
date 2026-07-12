# BUG-065 — `test_source_connection` : le subprocess `git ls-remote` en timeout n'est jamais tué

**Statut : 🟢 corrigé**

- **Zone** : backend / services/sources
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/sources.py:304-319`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`asyncio.wait_for(proc.communicate(), timeout=15)` annule l'attente mais laisse le process `git` tourner (et ses pipes ouverts) — pas de `proc.kill()` dans la branche `except TimeoutError`. Le token est aussi embarqué dans l'URL argv, visible dans la liste des process de l'hôte pour la durée du process.

## Scénario de défaillance

Des tests de connexion répétés contre un hôte black-holed accumulent des process `git` pendus jusqu'à épuisement des fd/process.

## Code concerné

```python
_, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=15)
...
except TimeoutError:
    return {"success": False, "message": "Délai dépassé (15 s)"}   # proc toujours vivant
```

## Piste de correction

`except TimeoutError: proc.kill(); await proc.wait()` ; passer les credentials via `http.extraheader`/askpass au lieu de l'URL.
