# BUG-091 — Prod : Caddy exige backend `service_healthy` sans `start_period` — boot lent (migrations) = site entier down

**Statut : 🟢 corrigé**

- **Zone** : infra / deploy/prod
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `deploy/prod/docker-compose.yml:37-42,76-80` (idem `docker-compose.build.yml:51-56,93-97`)
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le healthcheck backend (interval 15s, retries 5, pas de `start_period`) laisse ~75-90s au backend pour répondre. Or uvicorn ne sert `/health` qu'après le lifespan complet, qui inclut `apply_pending_for_all_workspaces` (migrations sur **toutes** les bases workspace, `main.py:152`). Caddy dépend de `backend: condition: service_healthy`.

## Scénario de défaillance

Instance prod avec plusieurs workspaces + une migration lourde (ex. reindex/ALTER sur grosses tables vectorielles) : backend dépasse 90s → marqué `unhealthy` → `docker compose up -d` échoue « dependency failed to start », **caddy ne démarre pas** → même le frontend statique et `/health` deviennent inaccessibles alors que le backend aurait fini de booter 2 min plus tard.

## Code concerné

```
    healthcheck:
      test: ["CMD", "python", "-c", "... urlopen('http://localhost:8000/health')"]
      interval: 15s
      timeout: 5s
      retries: 5        # pas de start_period
```

## Piste de correction

Ajouter un `start_period` généreux (ex. 300s) au healthcheck backend ; éventuellement assouplir la dépendance de caddy en `service_started`.
