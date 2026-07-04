# BUG-092 — `dev-deploy.sh` continue quand `.env` et `.env.example` sont absents — `--reset` silencieusement no-op puis `up` casse

**Statut : 🟢 corrigé**

- **Zone** : infra / dev-deploy.sh
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `dev-deploy.sh:245-247,278-286,305`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Si `.env` et `.env.example` manquent tous deux, le script imprime un simple warning et continue. `docker compose down -v` échoue alors sur l'interpolation `${POSTGRES_PASSWORD:?}` mais l'erreur est avalée par `|| true` → **la purge demandée par `--reset` n'a pas lieu**, puis `up -d` échoue plus loin avec un message d'interpolation sans rapport avec la cause racine.

## Scénario de défaillance

`./dev-deploy.sh --reset` sur un clone incomplet : l'admin croit avoir purgé postgres_data (le script l'a annoncé « ⚠ --reset : down -v (purge …) »), or rien n'a été purgé ; l'ancienne base ressurgit au déploiement suivant.

## Code concerné

```
  else
    echo "[2/5] ⚠  .env absent et .env.example introuvable — config requise pour démarrer"
  fi
...
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans || true
```

## Piste de correction

`exit 1` quand ni `.env` ni `.env.example` n'existent ; ne pas masquer l'échec du `down -v` en mode `--reset`.
