# BUG-033 — Un fichier poison bloque définitivement l'indexation de tous les fichiers suivants d'un job git

**Statut : 🟢 corrigé**

- **Zone** : backend / sync
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/sync/executor.py:741-793`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — gestion d'erreur par fichier + statut partiel de job

## Description

La boucle par fichier de `_execute_git_job` n'a aucune gestion d'erreur autour de `indexer.index_file`. Toute défaillance déterministe par fichier (`ChunkTooLargeError` d'un fence de code atomique surdimensionné, panic tree-sitter, erreur de contrainte DB) se propage, le job entier est marqué `error`, et `last_commit` n'avance pas. À chaque run suivant, le même fichier échoue au même point.

## Scénario de défaillance

Un repo contient un fichier markdown avec un fence mermaid de 50k tokens. `TokenNormalizer._emit_atomic` lève `ChunkTooLargeError` (classifié « permanent »). Chaque sync planifié échoue à ce fichier ; chaque fichier qui trie après lui dans le changeset n'est jamais indexé — définitivement — sans issue autre que retirer le fichier du repo.

## Code concerné

```python
for path in changes.added + changes.modified:
    ...
    await indexer.index_file(   # non protégé ; une exception avorte tout le job
        workspace_id=job.workspace_id, path=path, content=content, ...)
```

## Piste de correction

try/except par fichier, enregistrer le path fautif (ex. dans `index_job_files` avec un `change_type` `failed` ou dans le log de job), continuer, et refléter l'échec partiel dans le statut du job.
