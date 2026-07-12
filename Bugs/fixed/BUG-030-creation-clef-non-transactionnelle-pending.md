# BUG-030 — Création de clé non transactionnelle : lignes `'pending'` orphelines, et `GET /apikey` peut renvoyer la chaîne littérale `"pending"`

**Statut : 🟢 corrigé**

- **Zone** : backend / services/workspace_apikeys + api/admin
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/services/workspace_apikeys.py:100-122,162-186` ; consommateur `backend/src/rag/api/admin/__init__.py:156-165`
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — transaction + compensation, atomicité multi-étapes

## Description

`create_key`/`rotate_key` font un INSERT avec `api_key_ref='pending'` (autocommit — le router acquiert une connexion sans transaction), puis appellent Harpocrate `set_secret`, puis UPDATE la ref. Si `set_secret` échoue, la ligne avec un vrai fingerprint et `api_key_ref='pending'` persiste. `SecretResolver.resolve` laisse passer les chaînes non-ref telles quelles (`parse_ref` → None), donc `GET /workspaces/{name}/apikey` qui prend cette ligne renvoie `{"api_key": "pending"}` avec 200.

## Scénario de défaillance

Hoquet Harpocrate pendant `POST /workspaces` (première clé) → le workspace existe avec une ligne de clé la plus ancienne empoisonnée → les scripts de provisioning reçoivent `"pending"` comme clé API et échouent opaquement à la première utilisation ; la ligne est aussi comptée « active » dans `list_keys`.

## Code concerné

```python
key_id = await conn.fetchval(
    "INSERT INTO workspace_api_keys (...) VALUES ($1, $2, $3, 'pending') RETURNING id", ...)
...
await asyncio.to_thread(client.set_secret, path, api_key)   # échec = ligne 'pending'
```

## Piste de correction

Envelopper INSERT+set_secret+UPDATE dans une transaction et supprimer la ligne (ou marquer révoquée) en cas d'échec de l'écriture vault ; faire sauter les refs `'pending'` par `get_apikey`.
