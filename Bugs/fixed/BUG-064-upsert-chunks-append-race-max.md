# BUG-064 — `upsert_chunks(strategy="append")` : race MAX+1 read-then-insert sur `(path, chunk_index)`

**Statut : 🟢 corrigé**

- **Zone** : backend / db/workspace_embeddings
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/db/workspace_embeddings.py:52-68`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Deux indexations en mode append concurrentes pour le même path lisent toutes deux `MAX(chunk_index)` dans leurs propres transactions (READ COMMITTED) et calculent des plages d'index qui se chevauchent. Sur les tables legacy qui ont gardé `UNIQUE(path, chunk_index)`, une transaction échoue en UniqueViolation ; sur les tables migrées (contrainte droppée par la migration workspace 002), les deux réussissent et produisent des `chunk_index` **dupliqués**, corrompant l'ordre de présentation.

## Scénario de défaillance

Un job push et un sync planifié touchent le même path en stratégie append de façon concurrente.

## Code concerné

```python
raw = await conn.fetchval("SELECT COALESCE(MAX(chunk_index), -1) FROM embeddings WHERE path=$1", path)
```

## Piste de correction

`pg_advisory_xact_lock(hashtext(path))` par path avant la lecture du MAX.
