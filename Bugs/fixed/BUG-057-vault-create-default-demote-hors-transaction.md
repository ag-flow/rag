# BUG-057 — Vault `create(is_default=True)` démote le défaut courant hors de toute transaction

**Statut : 🟢 corrigé**

- **Zone** : backend / services/harpocrate_vaults
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/harpocrate_vaults.py:193-211`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`_DEMOTE_DEFAULT` (UPDATE tous les défauts à false) est exécuté, puis l'INSERT. Sur `UniqueViolationError` (nom dupliqué) — ou tout échec d'insert — le démote est déjà commité (autocommit, pas de `conn.transaction()`), laissant le système **sans vault par défaut**. `set_default` enveloppe correctement le même pattern dans une transaction ; `create` non.

## Scénario de défaillance

L'admin crée un vault avec un nom existant et `is_default=true` → 409 renvoyé, mais le vault par défaut précédent est silencieusement démoté → la création de workspace, la création de clé API, l'échange de token OIDC commencent tous à échouer avec « no default Harpocrate vault configured ».

## Code concerné

```python
if req.is_default:
    await conn.execute(_DEMOTE_DEFAULT)       # commité même si l'INSERT ci-dessous échoue
try:
    row = await conn.fetchrow(_INSERT_VAULT, ...)
except UniqueViolationError as exc:
    raise VaultNameAlreadyExistsError(req.name) from exc
```

## Piste de correction

Envelopper démote+insert dans `async with conn.transaction():`.
