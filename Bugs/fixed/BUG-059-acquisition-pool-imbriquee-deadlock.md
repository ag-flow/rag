# BUG-059 — Acquisition de pool imbriquée en tenant une connexion → deadlock par épuisement de pool

**Statut : 🟢 corrigé**

- **Zone** : backend / services/workspace_apikeys
- **Sévérité** : moyenne
- **Complexité** : simple mécaniquement, mais concurrence subtile
- **Fichiers** : `backend/src/rag/services/workspace_apikeys.py:29-39`, appelants ex. `backend/src/rag/services/workspaces.py:191-199`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — deadlock, chemin d'appel subtil

## Description

`create_key`/`rotate_key` reçoivent un `conn` tenu *et* le même `config_pool` ; `_get_vault_and_client` fait alors `config_pool.acquire()` pendant que la connexion de l'appelant est encore checked out. Le config pool a `max_size=5` par défaut (`WorkspacePoolRegistry`, `pool.py:26`). `acquire()` d'asyncpg n'a pas de timeout ici.

## Scénario de défaillance

5 créations concurrentes de workspace/clé API tiennent chacune une connexion et bloquent chacune dans `_get_vault_and_client` en attendant une 6e → deadlock permanent de tout le config pool ; chaque requête ultérieure touchant la DB pend.

## Code concerné

```python
async def _get_vault_and_client(vault_svc, client_provider, config_pool):
    async with config_pool.acquire() as conn:      # l'appelant tient déjà une autre conn de ce pool
        vault = await vault_svc.get_default(conn)
```

## Piste de correction

Passer le `conn` déjà tenu à `vault_svc.get_default(conn)` au lieu de le ré-acquérir, ou résoudre le vault avant d'acquérir la connexion externe.
