# BUG-096 — `docker-compose-dev.yml` : healthcheck postgres sans `start_period` — fenêtre de 25s pour l'initdb du premier boot

**Statut : 🟢 corrigé**

- **Zone** : infra / docker-compose-dev.yml
- **Sévérité** : basse
- **Complexité** : simple
- **Confiance** : faible
- **Fichiers** : `docker-compose-dev.yml:16-19`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

interval 5s × retries 5 = ~25s avant `unhealthy`. Au tout premier `up` (ou après `--reset`), l'image pgvector fait un `initdb` complet + création d'extension ; sur un LXC à stockage lent, 25s peuvent être dépassés. `backend` dépend de `service_healthy` → `docker compose up -d` échoue « container rag-postgres is unhealthy » alors qu'un retry 30s plus tard aurait réussi.

## Scénario de défaillance

Premier déploiement sur LXC avec stockage réseau/HDD → `dev-deploy.sh` échoue de façon non reproductible au deuxième lancement.

## Code concerné

```
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      retries: 5
```

## Piste de correction

Ajouter `start_period: 30s` au healthcheck postgres (dev et prod).
