# ag-flow.rag — Instructions Claude Code

## Projet

Service d'infrastructure RAG autonome (≠ module ag.flow) qui surveille des dépôts git, indexe leur contenu en base vectorielle pgvector et expose une API MCP de recherche sémantique consommable par les agents ag.flow et Claude Code. Provisionné une fois, partagé entre projets. Domaine public : `https://rag.yoops.org`. Spec complète : `specs/00-overview.md` (+ 12 fichiers numérotés).

**Standard de qualité** : code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis, pas de "c'est pas grave", pas de "on simplifiera plus tard". Chaque tâche est faite correctement ou pas du tout.

**Pas de quick-and-dirty, JAMAIS.** Quand tu présentes des options de design, ne propose PAS d'option "quick & dirty" / "hardcode" / "wire-it-up-and-clean-later". On fait toujours propre, tant pis pour l'effort. Si tu sens qu'une tâche est déraisonnable (>3 mois, scope qui explose, dépendance hors d'atteinte), **alerte explicitement l'utilisateur** plutôt que de proposer un compromis dégradé. L'utilisateur préfère qu'on découpe le chantier et qu'on en fasse correctement la part qu'on prend, plutôt que tout faire à moitié.

## Stack technique

- **Backend** : Python 3.12 + FastAPI + asyncpg (**pas SQLAlchemy**) + structlog JSON + pytest
- **Frontend (IHM `/ui`)** : Vite + React 18 + TypeScript strict + react-router-dom + TanStack Query + Tailwind + shadcn/ui + i18next + Vitest
- **BDD config** : PostgreSQL 16 (base `rag_config` — workspaces, sources, jobs, hashes, oidc) — source de vérité unique
- **BDD vectorielle** : PostgreSQL 16 + extension **pgvector** — une base `rag_{workspace_name}` dédiée par workspace, dimension fixée à la création selon le provider/modèle
- **Embedding providers** : OpenAI, Voyage AI, Ollama (pluggable, voir `specs/05-indexers.md`)
- **Sources** : git V1 (GitHub, Azure DevOps), extensible (url, confluence, notion, folder, s3 — voir `specs/09-roadmap.md`)
- **Secrets** : Harpocrate uniquement — formalisme déclaratif `${vault://...}` / `${env://...}` (cf. `specs/vault.md` et `specs/internal_resolution-formalism.md`). **Aucun secret en clair en base ni en config commitée.**
- **Auth** : double couche — OIDC Keycloak realm `homelab` (IHM `/ui`, rôles `rag-admin` / `rag-viewer`) + Bearer tokens opaques (master key + workspace api_keys) pour API REST/MCP
- **Reverse proxy prod** : Caddy (SSL géré par Cloudflare Tunnel en front, comme l'écosystème yoops)
- **Observabilité** : Loki + Grafana sur LXC 116 (`agflow-logs`), exposé sur `https://log.yoops.org` via Cloudflare tunnel, auth SSO Keycloak. Collecte via Grafana Alloy (Docker socket + journald). Rétention 7 jours.

## Dev & cible

- **Développement** : local Windows (uv + node), tests connectés à un Postgres + pgvector hébergés sur l'infra LXC
- **Intégration / cible MVP** : **LXC 303 (`rag`, 192.168.10.184, Ubuntu 24.04, Docker 29.4.3)** — user applicatif `agflow` (sudo + docker), répertoire `/opt/rag`, accès depuis Claude via `ssh pve "pct exec 303 -- ..."`. Init du répertoire faite manuellement par l'utilisateur (cf. `Install-dev.md`).
- **Stack logs** : LXC 116 (`agflow-logs`) déjà en place — le RAG y pousse ses logs via Alloy
- **Prod future** : à définir quand le MVP est validé

## Livraison test — UNIQUE workflow

**Toute livraison sur la machine de test passe par ces étapes et rien d'autre.** Pas de `scp`, pas de `rsync`, pas de build local poussé sur le LXC.

```bash
# 1. Commit sur la branche dev (toujours `dev`, jamais une autre)
git checkout dev
git add . && git commit -m "feat: ..."

# 2. Push
git push origin dev

# 3. Déploiement sur LXC 303 (rebuild + restart via le script idempotent)
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Le script `dev-deploy.sh` (à la racine du repo) fait : `git pull origin dev` → build images backend/frontend → `docker compose -f docker-compose.dev.yml down/up`. Initialisation initiale du répertoire `/opt/rag` : voir `Install-dev.md` (exécuté par l'utilisateur).

## Commandes essentielles

```bash
# Backend local (Windows)
cd backend && uv sync
cd backend && uv run uvicorn rag.main:app --reload          # :8000
cd backend && uv run pytest -v                              # Tests Python
cd backend && uv run ruff check src/ tests/                 # Lint
cd backend && uv run ruff format src/ tests/                # Format

# Frontend local (Windows)
cd frontend && npm install
cd frontend && npm run dev                                  # :5173 avec proxy /api -> :8000
cd frontend && npm test                                     # Vitest
cd frontend && npx tsc --noEmit                             # TS strict check
cd frontend && npm run lint                                 # ESLint
cd frontend && npm run format                               # Prettier

# Migrations DB (base rag_config uniquement — les bases pgvector workspace sont créées par l'API)
cd backend && uv run python -m rag.db.migrations            # Applique migrations en attente

# Debug LXC 303
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && docker compose -f docker-compose.dev.yml ps'"
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && docker compose -f docker-compose.dev.yml logs -f backend'"
```

## Layout du code

```
ag-flow.rag/
├── backend/
│   ├── pyproject.toml
│   ├── src/rag/
│   │   ├── main.py              # FastAPI app + lifespan (lance le sync worker)
│   │   ├── config.py            # Pydantic Settings (lit .env + résout ${vault://}/${env://})
│   │   ├── logging_setup.py     # structlog JSON
│   │   ├── api/                 # Routers FastAPI
│   │   │   ├── health.py
│   │   │   ├── admin.py         # /workspaces, /workspaces/{name}/sources, /workspaces/{name}/reindex (master key)
│   │   │   ├── workspace.py     # /workspaces/{name}/index (workspace api_key)
│   │   │   ├── mcp.py           # /mcp recherche sémantique (workspace api_key)
│   │   │   ├── oidc.py          # /auth/callback + session IHM
│   │   │   └── ui.py            # /ui (sert le build front, protégé OIDC)
│   │   ├── auth/                # Bearer (master + workspace) + OIDC Keycloak
│   │   ├── db/                  # asyncpg pool, helpers fetch_one/fetch_all/execute, migrations runner
│   │   ├── indexer/             # Chunking + embedding + upsert pgvector (provider-agnostic)
│   │   │   ├── providers/       # openai.py, voyage.py, ollama.py
│   │   │   └── engine.py        # Orchestration chunk → embed → upsert + dedup hash SHA-256
│   │   ├── sync/                # Sync worker (surveille les sources git, déclenche réindex)
│   │   ├── secrets/             # SecretResolver (formalisme ${vault://} / ${env://})
│   │   ├── services/            # Logique métier (workspace lifecycle, jobs, dedup)
│   │   └── schemas/             # DTOs Pydantic
│   ├── migrations/              # SQL bruts numérotés rag_config (001_init.sql, 002_oidc.sql…)
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── pages/               # Workspaces list/detail, Sources, Jobs, OIDC login
│       ├── components/
│       ├── hooks/
│       ├── lib/                 # api client, i18n
│       └── i18n/                # fr.json, en.json
├── docs/
│   ├── patterns/                # Design patterns (ref transversale)
│   ├── python-dev-rules.md      # Règles Python SOLID
│   ├── tests-python.md          # Couverture tests
│   ├── sonarQube.md             # Qualité code
│   ├── logs.md                  # Stack logs Loki/Grafana/Alloy
│   └── superpowers/plans/       # Plans de développement exécutés
├── specs/
│   ├── 00-overview.md           # Vue d'ensemble du service
│   ├── 01-data-model.md         # Schéma rag_config + pgvector
│   ├── 02-api-admin.md          # API administration (master key)
│   ├── 03-api-workspace.md      # API push synchrone (workspace key)
│   ├── 04-api-mcp.md            # API MCP recherche sémantique
│   ├── 05-indexers.md           # Providers, modèles, dimensions
│   ├── 06-secrets.md            # Résolution secrets via Harpocrate (RAG-spécifique)
│   ├── 07-deduplication.md      # Hash SHA-256
│   ├── 08-docker-init.md        # Script init container ag.flow
│   ├── 09-roadmap.md            # Extensions futures
│   ├── 10-auth.md               # OIDC Keycloak + Bearer tokens
│   ├── vault.md                 # Migration générique vers Harpocrate (ref transversale)
│   └── internal_resolution-formalism.md   # Formalisme ${vault://} / ${env://}
├── scripts/
│   ├── infra/                   # LXC Proxmox setup
│   ├── init-rag.sh              # Init container ag.flow (provisionne .rag-client.json)
│   └── deploy.sh                # Déploiement LXC cible
├── docker-compose.yml           # Dev : postgres + pgvector
└── docker-compose.prod.yml      # Prod : stack complète (backend + frontend + postgres + caddy)
```

## Conventions de code

### Python (backend)
- Python 3.12+, async/await partout
- **Pas de SQLAlchemy** — asyncpg direct avec helpers `fetch_one` / `fetch_all` / `execute` dans `db/pool.py`
- Pydantic v2 pour les DTOs, Pydantic Settings pour la config
- Logs structurés via `structlog.get_logger(__name__)` — **jamais** `print()` ; ne **jamais** loguer la valeur d'un secret résolu (loguer la clé logique uniquement)
- `type` hints partout, `from __future__ import annotations` en tête de fichier
- Fichiers max 300 lignes ; classes SRP ; méthodes 5-15 lignes
- Règles détaillées : `@docs/python-dev-rules.md`
- Règles tests : `@docs/tests-python.md`

### TypeScript (frontend)
- `strict: true`, `noUncheckedIndexedAccess: true`
- Composants fonctionnels + hooks, pas de classes
- React Query pour tout appel API, pas de `useEffect + fetch` direct
- i18n sur **tous** les labels affichés — `useTranslation()`, jamais de string brute
- Fichiers max 300 lignes
- Props typées via `interface`, exports nommés

### Base de données

- Migrations = fichiers SQL numérotés dans `backend/migrations/` (ex: `001_init.sql`, `002_oidc.sql`)
- Schéma géré en SQL brut, pas d'ORM
- Extensions requises sur `rag_config` : `pgcrypto` (UUID par défaut via `gen_random_uuid()`), `uuid-ossp` si besoin
- Extensions requises sur chaque base `rag_{workspace}` : `vector` (pgvector) — créée automatiquement à la création du workspace
- Index pgvector : `ivfflat (embedding vector_cosine_ops)` par défaut (cf. `specs/01-data-model.md`)
- Toute nouvelle table → migration SQL + test de migration
- **Règle de cohérence indexeur** : un workspace ne peut pas changer de provider/modèle sans réindexation complète (dimensions incompatibles). L'API renvoie `409 indexer_change_requires_reindex` (cf. `specs/02-api-admin.md`, `specs/05-indexers.md`)

### Secrets (Harpocrate)

Aucun secret n'est stocké en clair — ni en base, ni dans le code, ni dans les configs commitées. Tous les secrets sont référencés via le **formalisme déclaratif** :

```
${vault://<api_key_id>:<path>}      # secret dans Harpocrate
${env://<VAR_NAME>}                  # variable d'environnement / .env local (dev)
```

Spec complète : `specs/vault.md` (migration générique) + `specs/internal_resolution-formalism.md` (formalisme officiel) + `specs/06-secrets.md` (intégration RAG).

- Le seul secret d'amorçage en `.env` est le token Harpocrate (`HARPOCRATE_API_TOKEN_*`) + la `RAG_MASTER_KEY`
- Les `api_key_ref` (ex: `openai_embedding_key`) stockées en base sont des **clés logiques opaques** — le service ne connaît jamais le path physique
- Résolution paresseuse via `SecretResolver` à chaque usage ; valeur jamais persistée
- Cache RAM uniquement, invalidation sur `401`/`403`

### Tests
- **Backend** : pytest + pytest-asyncio ; fixture `client` (TestClient httpx) ; conteneur Postgres + pgvector éphémère pour les tests d'indexation
- **Frontend** : Vitest + React Testing Library ; `describe`/`it`, pas de `test`
- **TDD** : test rouge → impl → test vert → commit
- Mock du `SecretResolver` (pas d'appel réel à Harpocrate en CI) ; mocks des providers d'embedding pour les tests unitaires, smoke test E2E optionnel sur OpenAI/Voyage
- Couverture minimale par zone : voir `docs/tests-python.md`

## Règles de workflow

### Cycle de l'architecte
**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est pas une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Livraison
- Ne livre **jamais** le code ni en test ni sur git sans demande explicite
- Ne modifie pas `.env` sauf si demandé
- Commit messages en français, format conventionnel (`feat:`, `fix:`, `chore:`, `docs:`, `test:`…)

### Vérification avant validation
Avant de déclarer une tâche terminée, **toutes** ces étapes sont obligatoires :
1. Le code s'exécute sans erreur (lint + build)
2. Le cas nominal fonctionne (test unitaire ou manuel)
3. Les imports ajoutés existent réellement
4. Pas de régression sur les fichiers modifiés
5. Si modification frontend : la page charge sans erreur console
6. Si touche aux secrets : aucune valeur en clair dans les logs, aucun secret commité

### Discipline d'exécution
- Exécute directement, ne décris pas ce que tu vas faire — fais-le
- N'explique pas les étapes intermédiaires. Rapporte uniquement le résultat final
- Termine TOUTES les étapes d'un plan avant de faire un résumé
- Pas de raccourci "pour simplifier"
- Si tu rencontres un problème, signale-le et propose une solution — ne l'ignore pas silencieusement

## Outils Claude Code

### Context7 — documentation live
**Quand** : avant d'écrire du code qui utilise FastAPI, Pydantic v2, asyncpg, pgvector, openai-python, voyageai, Ollama, httpx, python-jose (OIDC), Authlib, React Query, Vite, React Router, i18next, Tailwind, etc. Les API évoluent, ne te fie pas à ta mémoire.

### Serena — navigation sémantique
**Quand** : avant un refactor, pour comprendre les dépendances entre modules (api ↔ services ↔ indexer ↔ db), ou pour trouver tous les usages d'une fonction/classe.

### Superpowers skills
- `writing-plans` : rédiger un plan d'implémentation TDD avant de coder
- `executing-plans` / `subagent-driven-development` : exécuter un plan tâche par tâche
- `systematic-debugging` : méthode pour debug un bug ou test qui échoue
- `test-driven-development` : discipline TDD rigoureuse
- `brainstorming` : explorer le design avant d'écrire quoi que ce soit
- `verification-before-completion` : vérifier que le travail est réellement fini avant de le dire

### /review
**Quand** : avant de présenter un changement multi-fichiers (>3 fichiers ou >100 lignes).

### /commit
**Quand** : quand l'utilisateur demande explicitement de committer. Format français conventionnel.

## Auto-amélioration

Quand tu fais une erreur ou que l'utilisateur te corrige :
- Ajoute une leçon dans `LESSONS.md`
- Format : `- [module] description courte de l'erreur et de la bonne pratique`
- Relis `@LESSONS.md` en début de tâche qui touche un module mentionné
- Ne dépasse pas 50 lignes — consolide les leçons similaires

## Notifications de skills

Quand tu invoques une skill via l'outil Skill, affiche systématiquement un marqueur visuel **avant** d'exécuter :

> **`🟢 SKILL`** → _nom-de-la-skill_ — raison en une phrase
