# BUG-089 — `dev-deploy.sh` exit 1 après un déploiement réussi si l'interface n'est pas `eth0`

**Statut : 🟢 corrigé**

- **Zone** : infra / dev-deploy.sh
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `dev-deploy.sh:154-157,321-326`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`detect_eth0_ip` est câblé en dur sur `eth0`. Si l'interface s'appelle autrement, le script sort en `exit 1` **après** que la stack soit up, et le smoke `/health` n'est jamais exécuté.

## Scénario de défaillance

Déploiement sur une VM Proxmox Debian (interface `ens18` — cas typique, ex. la VM de test `test1`) : la stack démarre correctement mais le script retourne 1. `remote-deploy.ps1` / une CI interprète ça comme un déploiement échoué ; l'admin cherche un bug applicatif inexistant.

## Code concerné

```
IP="$(detect_eth0_ip)"
if [ -z "$IP" ]; then
  echo "✗ Impossible de détecter l'IP eth0 ..." >&2
  exit 1
fi
```

## Piste de correction

Détecter l'IP de la route par défaut (`ip -4 route get 1.1.1.1 | awk '{print $7}'`) avec fallback eth0, ou dégrader en warning sans exit 1.
