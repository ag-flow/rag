# BUG-036 — `ssh_username` accepté de bout en bout mais jamais utilisé

**Statut : 🔴 à corriger**

- **Zone** : backend / sync/git_ops + sync/executor
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/sync/git_ops.py:136,258` (params), consommé à `sync/executor.py:638,695`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`clone()` et `list_remote_branches()` déclarent `ssh_username` mais leurs corps ne le référencent jamais — l'URL n'est pas réécrite et `ssh -l` n'est pas passé. L'UI/config (`services/sources.py:129-130`) le stocke, l'executor le transmet ; c'est silencieusement mort.

## Scénario de défaillance

Un utilisateur dont le serveur git exige un utilisateur SSH non-`git` (ex. Gerrit, `ssh://jdoe@host/repo`) met `ssh_username=jdoe` avec une URL style https ou host/path, s'attendant à ce que la plateforme construise l'URL SSH. Le clone tourne avec l'URL brute, l'auth échoue ou retombe en anonyme, sans indice de pourquoi le réglage n'a rien fait.

## Code concerné

```python
async def clone(*, url, branch, token, dest, ssh_key=None, ssh_username=None) -> None:
    ...  # ssh_username jamais référencé dans le corps
```

## Piste de correction

Soit appliquer `ssh_username` (réécrire l'URL en `ssh://<user>@...` ou ajouter `-o User=<user>` à `GIT_SSH_COMMAND`), soit rejeter le réglage au moment de la config.
