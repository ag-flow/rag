# BUG-086 — Caddyfile prod : route `/workspaces/*` morte — les timeouts étendus 120s ne s'appliquent jamais aux vrais endpoints

**Statut : 🔴 à corriger**

- **Zone** : infra / deploy/prod/Caddyfile
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `deploy/prod/Caddyfile:34-41`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le backend n'a aucune route racine `/workspaces` — le router workspace a `prefix="/api/workspaces"`. Le bloc `handle /workspaces/*` avec `read_timeout/write_timeout 120s` (prévu pour « gros payloads d'indexation ») ne matche donc jamais rien ; les requêtes réelles passent par `handle /api/*` avec les timeouts par défaut.

## Scénario de défaillance

Une indexation avec gros payload sur `/api/workspaces/...` dépasse le timeout par défaut du transport → 502/504 côté Caddy, alors que la config semble prévoir 120s. Bug silencieux : rien ne signale que la route est morte.

## Code concerné

```
    handle /workspaces/* {
        reverse_proxy backend:8000 {
            transport http {
                read_timeout 120s
```

## Piste de correction

Déplacer le transport 120s dans un `handle /api/workspaces/*` placé **avant** `handle /api/*` (les blocs `handle` sont évalués dans l'ordre d'apparition), ou supprimer le bloc mort.
