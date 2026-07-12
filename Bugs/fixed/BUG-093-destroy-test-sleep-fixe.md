# BUG-093 — `destroy-test.sh` : `sleep 2` fixe entre `pct stop` et `pct destroy` — destroy peut échouer sous `set -e`

**Statut : 🟢 corrigé**

- **Zone** : infra / scripts
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `scripts/destroy-test.sh:86-91`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`pct stop` est fire-and-forget (`|| true`) suivi d'un `sleep 2` fixe. Si l'arrêt prend plus de 2s (container chargé avec la stack Docker complète dedans), `pct destroy --purge` échoue « CT is running » et `set -e` interrompt le script, container laissé en place.

## Scénario de défaillance

LXC de test avec 5 containers Docker actifs → stop > 2s → destroy échoue, l'utilisateur doit refaire la manip à la main.

## Code concerné

```
ssh "${SSH_HOST}" "pct stop ${CTID} 2>&1 || true"
sleep 2
ssh "${SSH_HOST}" "pct destroy ${CTID} --purge"
```

## Piste de correction

Boucler sur `pct status` jusqu'à `stopped` (avec timeout), ou `pct stop` synchrone + retry sur destroy.
