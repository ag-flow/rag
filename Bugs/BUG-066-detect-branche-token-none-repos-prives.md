# BUG-066 — `add_source`/`update_source` détectent toujours la branche par défaut avec `token=None` → mauvaise branche pour les repos privés

**Statut : 🔴 à corriger**

- **Zone** : backend / services/sources
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/sources.py:133,216`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le commentaire prétend « token None si SSH », mais le token est `None` inconditionnellement, même quand `auth_ref` (PAT HTTPS) est présent et qu'un resolver est disponible (`update_source` reçoit même `resolver` et ne l'utilise jamais). Pour les repos privés, `detect_default_branch` échoue et le code retombe silencieusement sur `"main"`.

## Scénario de défaillance

Repo privé avec branche par défaut `develop`, source créée sans branche explicite → le workspace sync toujours `main` (ou échoue), avec juste un warning soft.

## Code concerné

```python
# Pour detect_default_branch : token None si SSH (fallback "main" acceptable)
config, branch_warning = await _resolve_branch_for_write(config, token=None)
```

## Piste de correction

Résoudre `auth_ref` et passer le token à `detect_default_branch`.
