# BUG-088 — `test-create-lxc.sh` : PAT GitHub embarqué dans l'URL de clone — persisté dans `.git/config` et visible dans `ps`

**Statut : 🔴 à corriger**

- **Zone** : infra / scripts
- **Sévérité** : moyenne (sécurité — fuite de PAT scope `repo`)
- **Complexité** : modérée
- **Fichiers** : `scripts/test-create-lxc.sh:379,384-396`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — sécurité, credential helper éphémère

## Description

`GIT_URL="https://${TOKEN}@github.com/${GIT_REPO}.git"` est interpolé dans la commande `pct exec … bash -c "…git clone … '${GIT_URL}' …"`. Le token (scope `repo`, accès à tout le compte) est : visible dans la liste de processus de l'hôte Proxmox et du LXC pendant le clone ; **persisté en clair** dans `.git/config` (remote origin) du LXC ; et une copie de `.env.git` est poussée dans `/root/.env.git`. Quand `CLEANUP=0` (défaut), le LXC reste sur le LAN avec le PAT dedans indéfiniment.

## Scénario de défaillance

Un LXC de test conservé « pour inspection » est compromis ou simplement accessible à un tiers du LAN → PAT à scope `repo` exfiltré via `cat /opt/*/.git/config`.

## Code concerné

```
GIT_URL="https://${TOKEN}@github.com/${GIT_REPO}.git"
...
git clone --branch '${GIT_BRANCH}' '${GIT_URL}' "$(basename '${APP_DIR}')"
```

## Piste de correction

Utiliser un credential helper éphémère (`git -c credential.helper=…` ou `http.extraHeader`) ou réécrire le remote sans token après clone (`git remote set-url origin https://github.com/...`), + fine-grained PAT limité au repo.
