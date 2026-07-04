# BUG-052 — `delete_git_credential` interroge une table `sources` inexistante

**Statut : 🔴 à corriger**

- **Zone** : backend / services/git_credentials
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/git_credentials.py:178-181`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le contrôle de référence interroge `FROM sources`, mais aucune migration ne crée de table `sources` — la table est `workspace_sources`. `asyncpg.UndefinedTableError` au runtime. Le test d'intégration qui l'attraperait nécessite `TEST_POSTGRES_PASSWORD` et était skippé au dernier run enregistré (349 skipped).

## Scénario de défaillance

Tout `DELETE` d'une credential git → 500 `relation "sources" does not exist`. Feature entièrement cassée.

## Code concerné

```python
ref_count = await conn.fetchval(
    "SELECT count(*) FROM sources WHERE config->>'auth_ref' LIKE $1",
    f"%{row['harpo_path']}%",
)
```

## Piste de correction

`SELECT count(*) FROM workspace_sources WHERE config->>'auth_ref' LIKE $1` (et noter que `LIKE` devrait échapper `%`/`_` dans le path, ou utiliser `=`/`position()`).
