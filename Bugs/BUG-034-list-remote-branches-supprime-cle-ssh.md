# BUG-034 — `list_remote_branches` supprime la clé SSH temporaire avant l'exécution de git

**Statut : 🔴 à corriger**

- **Zone** : backend / sync/git_ops
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/sync/git_ops.py:267-271`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le context manager `_ssh_key_env` est sorti immédiatement après `env.update(ssh_env)` ; son `finally` unlink le fichier de clé temporaire. Le subprocess est lancé après, avec `GIT_SSH_COMMAND=ssh -i <fichier-supprimé>`, donc l'auth SSH échoue toujours et la fonction renvoie `[]` (elle avale les erreurs par contrat).

## Scénario de défaillance

L'utilisateur configure une source privée avec `auth_type=ssh` et ouvre le sélecteur de branche dans l'UI : la liste de branches est toujours vide pour les sources SSH, sans erreur remontée.

## Code concerné

```python
if ssh_key is not None:
    with _ssh_key_env(ssh_key) as ssh_env:
        env.update(ssh_env)          # le contexte sort ici → fichier de clé unlinké
    auth_url = url
...
proc = await asyncio.create_subprocess_exec("git", "ls-remote", ...)
```

## Piste de correction

Garder le bloc `with _ssh_key_env(...)` ouvert autour de l'exécution du subprocess (comme le font `clone`/`pull`).
