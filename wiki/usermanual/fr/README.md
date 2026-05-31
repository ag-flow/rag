# ag-flow.rag — Manuel Utilisateur

**Version :** 1.0 · **Langue :** Français

---

## Sommaire

| # | Document | Description |
|---|---|---|
| 01 | [Installation](01-installation.md) | Prérequis, Docker, variables d'environnement, premier démarrage |
| 02 | [Première configuration](02-premiere-configuration.md) | Bootstrap admin, compte local, OIDC Keycloak |
| 03 | [Coffres Harpocrate](03-harpocrate.md) | Gestion des secrets, création et test des coffres |
| 04 | [Workspaces](04-workspaces.md) | Créer, configurer, chunking, clés API multi-rotation |
| 05 | [Sources git](05-sources-git.md) | Ajouter des dépôts, synchronisation, webhooks entrants |
| 06 | [Service MCP](06-mcp.md) | Connecter Claude Code au service RAG via le protocole MCP |
| 07 | [Playground](07-playground.md) | Chat RAG ancré sur le corpus |
| 08 | [Webhooks sortants](08-webhooks.md) | Notifications post-indexation vers vos systèmes |
| 09 | [Enrichissement LLM](09-enrichissement.md) | Triggers par extension, prompts templates, métadonnées |
| 10 | [Authentification OIDC](10-auth-oidc.md) | Keycloak, rôles, configuration SSO |
| 11 | [Référence API](11-api-reference.md) | Tous les endpoints, paramètres, exemples curl |
| 12 | [Agents Docker](12-agents-docker.md) | Initialisation automatique des containers ag.flow, `.rag-client.json` |
| 13 | [Déduplication](13-deduplication.md) | Hash SHA-256, jobs skippés, réindexation forcée |
| 14 | [Observabilité](14-observabilite.md) | Grafana, Loki, logs structurés, requêtes LogQL |
| 15 | [API Workspace programmatique](15-api-workspace-programmatique.md) | Indexation depuis une app ou un agent, CI/CD |
| 16 | [Credentials dans les coffres](16-credentials-coffres.md) | Clés API providers, tokens git, clés SSH |

---

## À propos de ce service

**ag-flow.rag** est un service d'infrastructure RAG (Retrieval-Augmented Generation) autonome et open source. Il indexe, maintient et expose des corpus documentaires via une API de recherche sémantique compatible avec le protocole MCP (Model Context Protocol) d'Anthropic.

### Ce qu'il fait

- **Indexe** des dépôts git automatiquement (GitHub, GitLab, Gitea, Bitbucket, Azure DevOps)
- **Stocke** les embeddings dans PostgreSQL + pgvector (une base isolée par workspace)
- **Expose** une interface de recherche sémantique via MCP pour Claude Code
- **Enrichit** les documents avec des métadonnées générées par LLM (triggers par extension)
- **Sécurise** tous les secrets via Harpocrate (zéro secret en clair en base)

### Architecture simplifiée

```
                    ┌─────────────────────────────┐
                    │         ag-flow.rag          │
                    │                              │
Claude Code ────────┤  POST /mcp/{workspace_id}   │
                    │                              │
Admin IHM ──────────┤  /ui/*  (OIDC Keycloak)     │
                    │                              │
API REST ───────────┤  /api/admin/*  (master key)  │
                    │                              │
GitHub webhook ─────┤  /api/webhooks/git/*        │
                    └──────┬─────────────┬─────────┘
                           │             │
                    PostgreSQL      Harpocrate
                    (rag_config)    (secrets)
                    + pgvector
                    (rag_{workspace})
```

---

## Démarrage rapide

Si vous avez déjà Docker et PostgreSQL, les étapes minimales sont :

```bash
# 1. Cloner le projet
git clone https://github.com/votre-org/ag-flow.rag
cd ag-flow.rag

# 2. Configurer l'environnement
cp .env.example .env
# Éditer .env avec vos valeurs

# 3. Démarrer
docker compose up -d

# 4. Accéder à l'interface
# http://localhost:8000/ui
```

Voir [Installation](01-installation.md) pour le guide complet.
