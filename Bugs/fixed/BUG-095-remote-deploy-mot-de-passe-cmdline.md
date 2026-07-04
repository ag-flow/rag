# BUG-095 — `remote-deploy.ps1` : mot de passe SSH exposé sur la ligne de commande plink

**Statut : 🟢 corrigé**

- **Zone** : infra / scripts
- **Sévérité** : basse (sécurité)
- **Complexité** : simple
- **Fichiers** : `scripts/remote-deploy.ps1:72` (et 65)
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`plink -batch -pw $remotePwd …` place le mot de passe en clair dans la ligne de commande — visible dans le Task Manager/`Get-Process`/journaux d'audit de processus Windows. S'ajoute `ssh -o StrictHostKeyChecking=no` qui désactive la protection MITM à chaque appel.

## Scénario de défaillance

Poste partagé ou audit d'endpoint (EDR journalisant les lignes de commande) : le mot de passe root du LXC de test est capturé en clair.

## Code concerné

```
plink -batch -pw $remotePwd -P $remotePort "${remoteUser}@${remoteHost}" $remoteCmd
```

## Piste de correction

Privilégier la clé SSH (déjà supportée) ; pour plink, utiliser `-pwfile` ; remplacer `StrictHostKeyChecking=no` par `accept-new`.
