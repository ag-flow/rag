# BUG-056 — `get_default_vault_name()` renvoie l'api_key_id, mais `source_webhooks` l'utilise comme *nom* de vault → enable/disable/rotate échouent toujours

**Statut : 🔴 à corriger**

- **Zone** : backend / secrets/client_provider + services/source_webhooks
- **Sévérité** : haute
- **Complexité** : modérée
- **Confiance** : moyenne
- **Fichiers** : `backend/src/rag/secrets/client_provider.py:100-103`, `backend/src/rag/services/source_webhooks.py:71-77,135-137,185-190`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — cohérence d'API, audit des consommateurs

## Description

`HarpocrateClientProvider._load` fait `self._default_name = next((v.api_key_id for v in vaults if v.is_default), None)` — l'**api_key_id**, pas `v.name`. `source_webhooks.enable_webhook` fait `vault_name = await client_provider.get_default_vault_name()` puis `vault_svc.get_by_name(conn, vault_name)` qui interroge `WHERE name = $1`. À moins qu'un vault ait `name` == `api_key_id`, ça renvoie `None` → `RuntimeError("Vault ... not found")`. Idem dans `disable_webhook` et `rotate_webhook_secret`. (D'autres consommateurs comme `oidc._token_request` ne renvoient la valeur qu'à `build_ref`/`get_client`, qui acceptent l'api_key_id, donc marchent — masquant l'incohérence.)

## Scénario de défaillance

L'admin active le mode webhook sur une source git → 500 « Vault '<api_key_id-ish>' not found ». Feature cassée dès que le nom du vault ≠ api_key_id.

## Code concerné

```python
self._default_name = next(
    (v.api_key_id for v in vaults if v.is_default),   # api_key_id, malgré le nom
    None,
)
```

## Piste de correction

Soit faire stocker `v.name` par `_load` (et auditer les consommateurs qui s'appuient sur les refs api_key_id), soit exposer deux méthodes explicites (`get_default_vault_name` vs `get_default_api_key_id`).
