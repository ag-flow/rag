# BUG-028 — `init-admin` : race count-then-insert autorise un 2e admin ; bcrypt bloque l'event loop

**Statut : 🔴 à corriger**

- **Zone** : backend / api/setup + services/local_auth
- **Sévérité** : moyenne (sécurité — création d'admin persistant par un attaquant)
- **Complexité** : simple mécaniquement, mais sensibilité concurrence/sécurité
- **Fichiers** : `backend/src/rag/api/setup.py:29-41` ; `backend/src/rag/services/local_auth.py:33` (`bcrypt.checkpw`)
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — race condition subtile + sécurité de bootstrap

## Description

Le `COUNT(*)`-puis-`INSERT` tourne dans une transaction READ COMMITTED par défaut : deux `POST /api/setup/init-admin` concurrents lisent tous deux count=0 et insèrent tous deux (des usernames différents ne violent aucune contrainte). L'endpoint est non authentifié par design (premier boot), donc la fenêtre de setup est exploitable par race. Séparément, `bcrypt.hashpw(..., gensalt(12))` (et `checkpw` au login) tournent en synchrone dans des handlers async, bloquant l'event loop ~100-300 ms par appel.

## Scénario de défaillance

Instance fraîche en cours de setup ; un attaquant poll `/api/setup/status` et tire `init-admin` en concurrence avec le propriétaire légitime → deux 201 → l'attaquant possède un compte admin persistant.

## Code concerné

```python
async with pool.acquire() as conn, conn.transaction():
    count = await conn.fetchval("SELECT COUNT(*) FROM users")
    if count > 0:
        raise SetupAlreadyDone()
    ...
    await conn.execute("INSERT INTO users ...")
```

## Piste de correction

`LOCK TABLE users IN EXCLUSIVE MODE` dans la transaction (ou un index partiel unique / advisory lock) pour qu'un seul insert passe le check ; exécuter bcrypt via `asyncio.to_thread`.
