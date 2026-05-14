# RAG Service — Vue d'ensemble

## Rôle

Service d'infrastructure autonome qui surveille des dépôts git, indexe leur contenu en base vectorielle, et expose une interface MCP consommable par les agents ag.flow et Claude Code.

Ce n'est pas un module ag.flow — c'est un **service d'infrastructure** au même titre qu'EMQX ou pgvector. Il est provisionné une fois et partagé entre projets.

## Responsabilités

- Gérer des **workspaces** isolés, chacun associé à un corpus et un indexeur
- Surveiller des **sources git** et réindexer les fichiers modifiés automatiquement
- Accepter des **indexations à la demande** (push synchrone)
- Éviter les réindexations inutiles via **hash de déduplication**
- Exposer une **API MCP** de recherche sémantique
- Résoudre les secrets via **Harpocrate** (jamais de secret en clair en base)

## Domaine public

```
https://rag.yoops.org
```

## Composants internes

```
rag-service/
├── API HTTP          — gestion workspaces + MCP (FastAPI)
├── Sync Worker       — surveille les sources git, déclenche réindexation
├── Indexer Engine    — chunking, embedding, upsert pgvector
├── Secret Resolver   — résolution des refs Harpocrate
└── Config DB         — PostgreSQL (paramétrage, jobs, hashes)
```

## Isolation par workspace

Chaque workspace dispose de :
- Sa propre base pgvector (dimension fixée selon l'indexeur)
- Sa propre api_key (obtenue via master key)
- Son propre indexeur (provider + modèle)
- Ses propres sources (git aujourd'hui, extensible)

## Relations avec l'écosystème

```
Harpocrate          → fournit les secrets (api keys providers)
ag.flow agents      → consomment le MCP au runtime
Claude Code local   → consomme le MCP via .rag-client.json
GitHub / Azure      → sources git surveillées
OpenAI / Voyage / Ollama → providers d'embedding
```

## Fichiers de cette spec

| Fichier | Contenu |
|---|---|
| 00-overview.md | Ce fichier |
| 01-data-model.md | Schéma base de données config |
| 02-api-admin.md | API administration (master key) |
| 03-api-workspace.md | API usage workspace (workspace key) |
| 04-api-mcp.md | API MCP recherche sémantique |
| 05-indexers.md | Providers, modèles, dimensions |
| 06-secrets.md | Résolution secrets via Harpocrate |
| 07-deduplication.md | Hash SHA-256, éviter réindexations |
| 08-docker-init.md | Script d'init container ag.flow |
| 09-roadmap.md | Extensions futures |
