# BUG-070 — AddSourceDialog : l'effet de défaut `ssh_username` écrase la valeur custom sauvegardée en édition

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/workspace
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `frontend/src/pages/workspace/AddSourceDialog.tsx:264-272`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — logique d'effet subtile (dirty/loaded), react-hook-form

## Description

L'effet se déclenche à chaque changement de `watchedProvider`/`watchedAuthType` et fait `setValue("ssh_username", defaultUser)` inconditionnellement. Ouvrir le dialog d'édition reset le formulaire depuis `source.config` (ex. `auth_type: "ssh"`, `ssh_username: "myuser"`) ; ce reset change les valeurs watchées (les défauts au mount étaient `token`/`github`), donc l'effet tourne juste après et écrase la valeur chargée par le défaut du provider (`"git"`, ou `""` pour gitea/azure-devops).

## Scénario de défaillance

Éditer une source SSH configurée avec un `ssh_username` custom ; le champ affiche silencieusement « git » à la place ; sauvegarder persiste le mauvais username et casse le clonage.

## Code concerné

```ts
useEffect(() => {
  if (!watchedProvider || watchedAuthType !== "ssh") return;
  const defaultUser = DEFAULT_SSH_USER[watchedProvider] ?? "";
  if (isEdit) { editForm.setValue("ssh_username", defaultUser); }
  else { createForm.setValue("ssh_username", defaultUser); }
}, [watchedProvider, watchedAuthType, ...]);
```

## Piste de correction

N'appliquer le défaut que sur un vrai changement piloté par l'utilisateur (dans les handlers `onChange` d'auth-type/provider), ou sauter quand la valeur vient d'être chargée depuis `source.config` / quand le champ est dirty.
