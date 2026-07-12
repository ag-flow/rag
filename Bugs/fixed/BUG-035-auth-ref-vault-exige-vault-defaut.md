# BUG-035 — Une ref vault explicite pour `auth_ref` exige à tort un vault par défaut

**Statut : 🟢 corrigé**

- **Zone** : backend / sync/executor
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/sync/executor.py:655-661`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Si `auth_ref` est déjà une ref vault complète (`${vault://name:key}`), `_resolve_token` la résout sans avoir besoin du vault par défaut (il vérifie `is_vault_ref`). Mais le garde lève `RuntimeError("no default Harpocrate vault configured")` dès que `auth_ref` est défini et qu'aucun vault par défaut n'existe, même pour des refs pleinement qualifiées.

## Scénario de défaillance

Déploiement sans vault par défaut, source configurée avec `auth_ref="${vault://prod:GH_TOKEN}"` — ref parfaitement résolvable. Chaque job git échoue avec « no default Harpocrate vault configured » alors que la résolution aurait réussi.

## Code concerné

```python
if config.get("auth_ref") and default_vault_name is None:
    raise RuntimeError("no default Harpocrate vault configured")
token = (await _resolve_token(resolver, config, default_vault_name)
         if default_vault_name is not None else None)
```

## Piste de correction

Ne lever que quand `auth_ref` est une clé logique nue (`not is_vault_ref(auth_ref)`) et qu'aucun vault par défaut n'existe ; toujours appeler `_resolve_token` pour les refs vault.
