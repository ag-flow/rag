# RAG Service — Roadmap

## Livré en V1

- Workspaces isolés avec pgvector dédié
- Sources git (GitHub, Azure DevOps)
- Indexeurs : OpenAI, Voyage AI, Ollama
- Déduplication par hash SHA-256
- Indexation push synchrone
- API MCP multi-workspaces
- Résolution secrets via Harpocrate
- Script d'init Docker idempotent

---

## Extensions prévues

### Nouvelles sources (`workspace_sources.type`)

Le modèle de données est conçu pour être extensible. Les sources futures s'ajoutent sans modifier le schéma principal.

| Type | Description |
|---|---|
| `url` | Crawler web, documentation en ligne |
| `confluence` | Pages Confluence Pickup/DOSI |
| `notion` | Pages Notion |
| `folder` | Dossier local monté en volume |
| `s3` | Bucket S3 ou compatible |

---

### Amélioration du chunking

✅ Infrastructure backend livrée en M9 — cf. `docs/superpowers/specs/2026-05-18-M9-backend-chunking-infrastructure-design.md`.
✅ Frontend livré en M9b — onglet `Chunking` dans `WorkspaceDetailPanel`, cf. `docs/superpowers/specs/2026-05-19-M9b-frontend-chunking-design.md`.

Pattern factory + registry par stratégie côté backend, config par workspace (table `chunking_configs`), champ `embeddings.metadata jsonb` prêt, runner de migrations workspace au boot. Une seule stratégie disponible : `paragraph` (algo historique).

Stratégies futures (jalons distincts) :
- Chunking sémantique (respect des sections Markdown)
- Chunking par blocs de code
- Métadonnées de chunk enrichies (titre de section parent, type de contenu)

---

### Reranking

✅ Livré en M8 — cf. `docs/superpowers/specs/2026-05-17-M8-backend-reranking-design.md`.

Config par workspace (table `rerank_configs`), 3 providers :
- Cohere Rerank API
- Voyage AI Rerank
- Ollama local (BGE / Jina)

Fail-fast si le provider tombe (cohérent avec `mcp.py`).

Frontend livré en M8b (onglet "Rerank" dans `WorkspaceDetailPanel`) — cf. `docs/superpowers/specs/2026-05-18-M8b-frontend-rerank-design.md`.

---

### SDK Harpocrate phase 2

Sécurisation du `HARPOCRATE_TOKEN` dans le `.env` via le SDK Harpocrate. Transparent pour le service RAG — aucune modification requise.

---

### Intégration ag.flow

Le service RAG sera référencé dans la partie Docker d'ag.flow comme ressource d'infrastructure. Les agents Docker auront accès au contexte de leur workspace via MCP sans configuration manuelle au-delà du `docker-compose.yml`.
