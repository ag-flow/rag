# BUG-097 — `dev-deploy.sh` : URLs finales trompeuses — « IHM » sur `/` (bandeau Caddy) et psql sur la base `postgres`

**Statut : 🟢 corrigé**

- **Zone** : infra / dev-deploy.sh
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `dev-deploy.sh:354,359`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le récap final annonce `→ IHM (frontend) : ${APP_URL}/` alors que `/` renvoie le `respond` texte de Caddy (l'UI est sous `/ui/`) ; et la ligne psql pointe la base `postgres` au lieu de `rag_config` (la base applicative).

## Scénario de défaillance

Un nouvel arrivant ouvre `${APP_URL}/`, voit un bandeau texte, conclut que le front est cassé ; ou se connecte en psql sur la mauvaise base et ne trouve aucune table.

## Code concerné

```
  → IHM (frontend)   : ${APP_URL}/
  ...
  → Postgres CLI     : psql postgresql://rag:<POSTGRES_PASSWORD>@${IP}:5432/postgres
```

## Piste de correction

Afficher `${APP_URL}/ui/` et `/rag_config`.
