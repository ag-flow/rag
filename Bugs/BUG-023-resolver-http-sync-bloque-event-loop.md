# BUG-023 — `SecretResolver` fait du HTTP synchrone bloquant sur l'event loop

**Statut : 🔴 à corriger**

- **Zone** : backend / secrets
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/secrets/resolver.py:175` (`client.get_secret(path)`) ; contraster avec `api/playground.py:121` et `api/admin/__init__.py:323` qui utilisent `asyncio.to_thread`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — envelopper dans `asyncio.to_thread`

## Description

`_vault_lookup_cached` est `async` mais appelle le SDK Harpocrate synchrone (`HarpocrateVaultClient.get_secret` → `self._sdk.secrets.get`, un appel HTTP style requests) directement. Chaque résolution de secret en cache-miss (auth bearer workspace, auth MCP, OIDC, webhooks git, indexer) gèle tout l'event loop pendant la durée du round-trip HTTP (ou du timeout).

## Scénario de défaillance

Harpocrate lent/en timeout (ex. 10 s de connect timeout) → une seule requête cache-miss bloque **toutes** les requêtes concurrentes, y compris `/health`, pendant tout le timeout ; sous charge, cela cascade en indisponibilité totale.

## Code concerné

```python
try:
    value = client.get_secret(path)   # HTTP sync dans un async def
```

## Piste de correction

Envelopper `client.get_secret` dans `asyncio.to_thread` à l'intérieur du resolver (comme le codebase le fait déjà ailleurs).
