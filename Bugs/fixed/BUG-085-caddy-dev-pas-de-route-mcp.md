# BUG-085 — Caddyfile dev : aucune route `/mcp` — l'endpoint MCP annoncé par dev-deploy.sh est absorbé par le catch-all

**Statut : 🟢 corrigé**

- **Zone** : infra / Caddyfile + dev-deploy.sh
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `Caddyfile:17-51`, `dev-deploy.sh:356`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le Caddyfile dev n'a aucun `handle /mcp*`, alors que le backend expose `/mcp` (router POST + mount ASGI `/mcp/{workspace_id}`) et que `dev-deploy.sh` affiche `→ API MCP : ${APP_URL}/mcp` en fin de déploiement. Toute requête `/mcp*` sur le port 80 tombe dans le catch-all `respond … 200`.

## Scénario de défaillance

Un dev suit la sortie du script, branche un client MCP sur `http://<ip>/mcp/<uuid>` → 200 texte au lieu du serveur MCP. Ça ne marche qu'en bypassant Caddy sur `:8000` (non documenté pour ce cas).

## Code concerné

```
    handle /redoc* {
        reverse_proxy backend:8000
    }
    handle /ui* {          # ← pas de handle /mcp nulle part
```

## Piste de correction

Ajouter `handle /mcp* { reverse_proxy backend:8000 }` au Caddyfile dev (aligné sur le fix prod BUG-084).
