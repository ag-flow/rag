# BUG-071 — AddSourceDialog : `credential_ref` non réinitialisé au changement d'auth type → ref de token soumise comme `ssh_key_ref`

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/workspace
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/AddSourceDialog.tsx:312-314,334-336,619-639`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Basculer entre « token » et « ssh » échange la liste des credentials, mais la valeur `credential_ref` du formulaire est conservée. Le Select affiche alors le placeholder (valeur absente de la nouvelle liste) tandis que le formulaire tient toujours l'ancien path harpo. `buildCreatePayload`/`buildUpdatePayload` routent ce qui est dans `credential_ref` vers `auth_ref` ou `ssh_key_ref` selon le seul `auth_type`.

## Scénario de défaillance

L'utilisateur sélectionne un token git, puis passe l'auth en SSH, voit un sélecteur de clé apparemment vide, soumet → un path harpo de token git est envoyé comme `ssh_key_ref` ; le clone échoue plus tard avec une erreur d'auth confuse. La même valeur périmée alimente aussi l'appel de détection de branche.

## Code concerné

```ts
const authRef = v.auth_type === "token" ? (v.credential_ref || undefined) : undefined;
const sshKeyRef = v.auth_type === "ssh" ? (v.credential_ref || undefined) : undefined;
```

## Piste de correction

Réinitialiser `credential_ref` (et re-valider) dans le `onChange` du Controller `auth_type`.
