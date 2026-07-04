# BUG-060 — I/O synchrone bloquant dans les chemins async (méthodes du service HarpocrateVaults + bcrypt)

**Statut : 🔴 à corriger**

- **Zone** : backend / services/harpocrate_vaults + services/local_auth
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/harpocrate_vaults.py:329,363,426-431,477,517,566,591`, `backend/src/rag/services/local_auth.py:33-36`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)
- **Lié** : BUG-023 (même défaut dans `secrets/resolver.py`), BUG-028 (bcrypt)

## Description

`HarpocrateVaultsService.test_connection/get_wallet_info/list_types/list_wallet_secrets/write_secret/delete_secret` font des appels HTTP synchrones sans `asyncio.to_thread` (d'autres services — `git_credentials`, `ssh_keys`, `workspace_apikeys` — enveloppent systématiquement le même client dans `to_thread`). `LocalAuthService.verify` exécute `bcrypt.checkpw` (~100 ms par design) sur l'event loop.

## Scénario de défaillance

Harpocrate lent/injoignable (timeout de plusieurs secondes) : un seul appel gèle tout l'event loop — toutes les requêtes concurrentes, healthchecks et le scheduler de sync stallent pendant toute la durée. Idem chaque login sérialise ~100 ms de bcrypt.

## Code concerné

```python
# ex. harpocrate_vaults.py
info = client.get_wallet_info()   # HTTP sync dans un async def
# local_auth.py
if not bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
```

## Piste de correction

Envelopper tous les appels SDK et `bcrypt.checkpw` dans `asyncio.to_thread`.
