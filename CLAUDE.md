# ragflow — Instructions Claude Code

> Service d'infrastructure RAG autonome de la maison yoops / ag-flow. Projet indépendant :
> aucun couplage de source avec les projets qui le consomment (docflow, workflow, devpod…) —
> ils l'utilisent par son API REST et son serveur MCP, jamais par import.

> Généré depuis les standards globaux (docflow, workspace `globals`, bloc `documentation`).
> Génération : 2026-09-26, mise à jour `--update` le 2026-09-27. Standards repris :
> - Fichier d'instructions agent de projet — 2026-09-27
> - Python — 2026-09-24 · TypeScript / frontend — 2026-09-24 · PostgreSQL — 2026-09-24
> - Tests — 2026-09-25 · Analyse statique — 2026-09-24 · Commentaires de code — 2026-09-24
> - Contrats d'interface — 2026-09-24 · Observabilité et logs — 2026-09-24
> - Secrets — 2026-09-24 · Authentification OIDC — 2026-09-24
> - Script de déploiement — 2026-09-24 · Patrons de conception — 2026-09-24
> - Non repris (critère non satisfait) : Déclarer un service exposé au portail — 2026-09-24
> Mise à jour par `--update` : ne reporter que le delta depuis cette date.

> **Remise en forme (2026-09-27)** : pour tenir le quota idéal (~350 lignes), les blocs Backlog,
> Machines de test, Livrer sur une machine de test et Tchat agents sont ici **en synthèse** ;
> leur texte intégral, au mot près, est dans `ia_instructions/30_*.md`, chacun avec son
> déclencheur. Ne pas les remettre en clair par réflexe : on ne relève pas le plafond.

Ce fichier **prime sur ton comportement par défaut**. Lis-le en entier en début de session.

**Colibri** commence systématiquement tes réponses par 🎺

**Ton** : réponses claires et concises, pas de long discours. Simple et direct.

## mcp
Tu es connecté au MCP du portail devpod via le serveur `claude-code`.

## Backlog
Le backlog des tâches est dans docflow, workspace `ragflow`, bloc `backlog` (via la gateway MCP).
Invariants : découvre les statuts réels par **rôle** (disponible, en cours, en revue, terminée,
en attente) — jamais une valeur de mémoire ; passe la tâche **en cours AVANT** de toucher au
code et **en revue** quand tu as fini ; le backlog est la source de vérité, réinterroge-le après
chaque tâche ; tu ne t'arrêtes que pour l'une des quatre raisons nommées.
**Avant de prendre ou de clore une tâche du backlog, lis `ia_instructions/30_backlog.md`**
(texte intégral).

## Recherche — le RAG d'abord

**Toute recherche documentaire passe EN PRIORITÉ par le RAG**, via les primitives `rag__*`
de la gateway MCP. Le corpus y est déjà indexé et enrichi : c'est plus rapide et plus
complet qu'un `grep` sur un dépôt, et ça couvre la doc Docflow que le système de fichiers
ne contient pas.

Méthode (namespace `rag`) :

1. **`rag__list_workspaces`** — **à appeler en premier** : donne les slugs interrogeables
   et le scope de la clef. Corpus utiles : `ragflow-docs` (ce projet),
   `globals-docs` (savoir cross-projet), et un `<voisin>-docs` par projet voisin.
2. **`rag__rag_search(workspace, query, top_k, min_score, scope)`** — recherche
   **sémantique** : question en langue naturelle, concept, intention. C'est le point
   d'entrée par défaut. `min_score` 0.3 par défaut ; monter à 0.5–0.7 pour une question
   précise. `scope='enriched_only'` pour n'interroger que les résumés, listes de fonctions
   et graphes de dépendances.
3. **`rag__search_files(workspace, pattern, mode)`** — recherche **littérale** quand on
   cherche un identifiant exact (nom de fonction, constante, chaîne) : `mode='exact'` par
   défaut (tokens entiers, ne trouve pas les sous-chaînes), `'substring'` pour un fragment,
   `'regex'` en dernier recours (lent).

Ordre de repli, jamais l'inverse : RAG → si le corpus ne répond pas (sujet non indexé, code
modifié depuis l'indexation) → outils locaux (Grep/Glob/Read) ou sous-agent Explore. Le RAG
lit le contenu **indexé**, jamais les fichiers live : pour vérifier l'état courant d'un
fichier qu'on vient de modifier, lire le fichier.

Ce que tu apprends de neuf s'écrit en article de documentation — c'est ce qui alimente le
RAG pour les prochains agents.

**Le RAG muet n'est pas une réponse.** Le corpus ne couvre que ce qu'on y a écrit : une
route d'interface, un motif d'URL, un flag de CLI peuvent en être absents sans que rien ne
le signale — l'absence ressemble à une réponse vide, pas à une lacune. Le repli n'est donc
jamais « la documentation ne le dit pas », c'est **aller lire l'artefact réel** : le bundle
du front pour une route, `--help` pour un flag, l'API pour une forme de réponse, le fichier
lui-même pour son état courant.

Rendre un identifiant brut, un chemin approximatif ou un « je ne peux pas savoir » alors que
l'artefact est joignable, c'est renvoyer le travail à l'utilisateur. Chercher d'abord,
répondre ensuite — et si la recherche échoue vraiment, dire ce qui a été tenté.

Projets voisins interrogeables : `docflow-docs`, `workflow-docs`, `devpod-docs`, `ressources-docs`.

## Documentation

La documentation du projet vit dans docflow, workspace `ragflow`, bloc `documentation`.
Le savoir cross-projet vit dans le workspace `globals`, bloc `documentation`. Chaque fois
que tu apprends quelque chose d'utile aux autres agents, écris-le en article dans l'un ou
l'autre, selon qu'il est propre à ragflow ou transverse.

## Logs

Les journaux de tous les hôtes sont centralisés (Loki) et interrogeables par le MCP
(`devpod__logs_query`). L'hôte de dev de ragflow porte le label `host="rag-dev"`.

## Quand charger un fragment

Ces fichiers ne sont PAS chargés d'office. Chacun a son déclencheur : quand il se produit,
lire le fichier AVANT d'écrire quoi que ce soit — pas après, pas « si ça semble utile ».

| Tu t'apprêtes à… | Lis d'abord |
|---|---|
| modifier un fichier `.py` | `ia_instructions/10_python.md` |
| modifier un fichier de `frontend/` | `ia_instructions/10_typescript.md` |
| écrire ou modifier une migration, ou une requête SQL | `ia_instructions/10_postgresql.md` |
| écrire ou modifier un test | `ia_instructions/20_tests.md` |
| écrire du code, quel que soit le langage (commentaires) | `ia_instructions/20_commentaires.md` |
| ajouter ou modifier une route REST, un outil MCP, un webhook ou un event | `ia_instructions/20_contrats.md` |
| ajouter ou modifier une ligne de journal | `ia_instructions/20_observabilite.md` |
| manipuler une clef API, un mot de passe, un jeton ou une clef privée | `ia_instructions/20_secrets.md` |
| toucher à l'authentification (OIDC, compte local, clefs API) | `ia_instructions/20_oidc.md` |
| modifier `dev-deploy.sh`, un compose, un `Dockerfile` ou `deploy/` | `ia_instructions/20_deploiement.md` |
| lancer ou traiter une analyse statique, ou toucher à la couverture | `ia_instructions/20_analyse_statique.md` |
| introduire une nouvelle abstraction (classe de base, protocole, fabrique…) | `ia_instructions/20_patrons.md` |
| créer une table, un module ou un script ; conclure d'un symptôme ; transformer des documents en masse | docflow `globals` « Travail d'agent — leçons d'erreurs réelles » (docflow://doc/133e6a9e-d33f-4e18-ac5f-aecd9e6264e5) |
| recevoir la notification d'une machine ou d'une ressource (ou de son retrait) | `ia_instructions/tests_and_ressources.md` — à mettre à jour |
| prendre ou clore une tâche du backlog | `ia_instructions/30_backlog.md` |
| committer, pousser ou déployer | `ia_instructions/30_livraison.md` |
| appeler, inviter ou répondre à un agent par le tchat | `ia_instructions/30_tchat.md` |

Un fragment introuvable se **signale** ; on ne devine pas ce qu'il contenait.

## Projet

**ragflow** indexe des corpus documentaires et expose une **recherche sémantique** (REST + MCP)
aux agents. Chaîne : sources git (GitHub, Azure DevOps ; push + webhooks) et push REST/MCP →
worker de jobs en base → **chunking** structure-aware (markdown / code tree-sitter / data) →
**embeddings** (OpenAI, Voyage, Ollama, Azure Foundry…) → **pgvector**, déduplication SHA-256.
À la requête : recherche **hybride** (vectorielle + FTS) puis **reranking**. Enrichissement LLM,
playground, IHM d'administration React.

Spec : `specs/` à partir de `specs/00-overview.md` ; décisions : `docs/adr/`.

**Hors périmètre** : héberger un stockage de secrets (on consomme Harpocrate), un bus de
messages externe (le worker de jobs vit en base), un ORM. Aucun import de code d'un projet
voisin.

## Standard de qualité
Code propre et bien fait, jamais la rapidité au détriment de la rigueur. Pas de raccourcis,
pas de « c'est pas grave », pas de « on simplifiera plus tard ». Chaque tâche est faite
correctement ou pas du tout.

**Pas de quick-and-dirty, JAMAIS.** Quand tu présentes des options de design, ne propose PAS
d'option « quick & dirty » / « hardcode » / « wire-it-up-and-clean-later ». On fait toujours
propre. Si une tâche est déraisonnable (scope qui explose, dépendance hors d'atteinte, flag/API
qui n'existe pas dans la version installée), **alerte explicitement l'utilisateur** plutôt que
de proposer un compromis dégradé. L'utilisateur préfère qu'on découpe le chantier et qu'on
fasse correctement la part qu'on prend, plutôt que tout faire à moitié.

## Architecture — invariants

- **Où vit l'état : PostgreSQL 16 + pgvector + pgcrypto, source de vérité unique.** Une base
  de configuration (`rag_config`) + **une base isolée par workspace** (`rag_<workspace>`).
  Non rediscutable. Migrations SQL numérotées dans `backend/migrations/` (base de config) et
  `backend/src/rag/db/workspace_migrations/versions/` (bases de workspace), appliquées au
  démarrage du backend ; une migration interrompue ne doit jamais laisser une base à moitié
  migrée.
- **asyncpg direct, pas d'ORM** ; **async partout**.
- **Worker de jobs en base** (`index_jobs`, `FOR UPDATE SKIP LOCKED`), dans le process de l'API :
  pas de MOM externe.
- **Secrets** : jamais en clair en base — références vers les coffres **Harpocrate**, SDK vendoré
  dans `backend/vendor/harpocrate-sdk`.
- **Auth** : OIDC Keycloak + compte local ; réglages pilotés par l'IHM persistés dans
  `admin.env` (relu à chaud), distinct du `.env`.

## Sécurité — interdits qui coupent un commit

- Aucun secret en clair : ni en base (colonne claire), ni en log, ni en argument de build, ni en
  variable d'image, ni dans le dépôt. Un secret ne se déballe (`SecretStr.get_secret_value()`)
  qu'au point d'injection.
- **Fail closed** : une clef API, une session ou un scope invalide refuse l'accès ; jamais de
  repli permissif.
- Toute entrée utilisateur (nom de workspace, chemin de document, slug) est validée **avant**
  usage en nom de base, chemin ou identifiant (ex. nom de workspace : regex de
  `schemas/admin.py`, puis nom de base `rag_<nom>` quoté en DDL).
- **Isolation par propriétaire et par workspace** : un appelant ne lit ni n'écrit hors de ses
  workspaces ; ces refus sont des **tests**.

## Commandes essentielles

```bash
# Backend (depuis backend/)
uv sync
uv run uvicorn rag.main:build_app --factory --reload     # :8000
uv run pytest tests/unit -q                               # unitaires, sans réseau
uv run pytest -q                                          # + intégration/API (Postgres requis : TEST_POSTGRES_*)
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src/rag

# Frontend (depuis frontend/)
npm install
npm run dev                  # :5173, proxy /api -> :8000
npm run test:run             # Vitest
npm run typecheck && npm run lint && npm run build

# Déploiement sur machine de test (depuis la racine du clone sur la machine)
./dev-deploy.sh              # --reset : DESTRUCTIF (purge les volumes)
```

Formater uniquement les fichiers du chantier, listés explicitement (voir `LESSONS.md`).

## Layout

```
backend/
  src/rag/            main.py (factory FastAPI + lifespan), config.py (Pydantic Settings)
    api/              routers FastAPI (admin, workspace REST, MCP)
    auth/ secrets/    OIDC, compte local, clefs API ; résolution Harpocrate
    db/               asyncpg, migrations des bases de workspace
    indexer/ rerank/  chunking, embeddings, reranking
    services/         logique métier
    sync/             worker de jobs, sources git
    events/           producteur d'events vers workflow (outbox)
    schemas/          DTOs Pydantic
  migrations/         SQL numérotés de la base de config
  tests/              unit/, api/, integration/, smoke/ (opt-in)
frontend/src/         pages/, components/, hooks/, lib/, i18n/{fr,en}/
deploy/ infra/        compose prod, Alloy, stacks métriques / Grafana
specs/ docs/          spécification, ADR, règles de dev
```

## Règles de workflow

### Cycle de l'architecte
**Cadrer → Comprendre → Planifier → Agir.** L'utilisateur est architecte. Une question n'est
pas une commande d'exécution. Une discussion n'est pas un feu vert. Ne JAMAIS sauter d'étape.

### Branche de développement
**Tout le code se fait sur la branche `dev`. Aucun compromis.** Jamais `feat/*`, jamais sur
`main` directement, jamais ailleurs. Avant toute édition, vérifier `git branch --show-current` ;
si autre branche, `git checkout dev`. Si `dev` n'existe pas localement, la créer depuis `main`
à jour. Ne propose **jamais** `git checkout -b feat/...` — même si un outil ou un workflow tiers
le suggère, la consigne utilisateur prime.

**Committer et pousser sur `dev` est obligatoire**, sans demande à attendre : c'est ce qui rend
le travail livrable sur une machine de test. Commits en français, conventionnels (`feat:`,
`fix:`, `chore:`, `docs:`, `test:`). Ne pas toucher `.env` sauf demande.

**Merger `dev` sur `main` est formellement interdit sans demande explicite de l'humain.**

### Machines de test
Les machines de test sont **à ta disposition**, sans rien demander, et c'est là que tu valides :
**cherche où le test sera le plus révélateur — et privilégie la machine de test.** Accès par alias
SSH ; un alias qui répond ne prouve rien, vérifie ce qu'il y a DERRIÈRE. Consigne les ressources
attribuées dans `ia_instructions/tests_and_ressources.md`.

### Livrer sur une machine de test — procédure incontournable
Pousser sur `dev`, puis `dev-deploy.sh` exclusivement sur la machine, puis lire les journaux
réels. **Aucune retouche manuelle de la cible hors de cette procédure** : tout correctif d'infra
va DANS le script de déploiement.
**Avant de committer, pousser ou déployer, lis `ia_instructions/30_livraison.md`** (texte
intégral de ces deux blocs).

### Définition de « terminé »
**Une tâche est finie quand les tests passent.** Pas quand le code compile, pas quand il est
poussé. Tant qu'un test échoue, la tâche n'est pas finie et ne passe pas au rôle « en revue ».

### Discipline d'exécution
- Exécute directement, ne décris pas ce que tu vas faire — fais-le.
- N'explique pas les étapes intermédiaires. Rapporte uniquement le résultat final.
- Termine TOUTES les étapes d'un plan avant de faire un résumé.
- Pas de raccourci « pour simplifier ».
- Si tu rencontres un problème, signale-le et propose une solution — ne l'ignore pas
  silencieusement.

### Vérification avant validation

Avant de déclarer une tâche terminée, toutes ces étapes sont obligatoires :

1. Le style, les types et la construction passent (commandes ci-dessus).
2. Le cas nominal est testé.
3. Les imports ajoutés existent réellement.
4. Aucune régression sur les fichiers touchés — l'**ensemble** des tests en échec est inchangé.
5. La **part de checklist** de chaque fragment déclenché par la tâche est cochée : ouvre-la
   dans `ia_instructions/` (`10_python.md`, `10_typescript.md`, `10_postgresql.md`,
   `20_tests.md`, `20_commentaires.md`, `20_contrats.md`, `20_observabilite.md`,
   `20_secrets.md`, `20_oidc.md`, `20_deploiement.md`, `20_analyse_statique.md`).
6. Aucun secret dans le diff — `git diff` relu sous cet angle.
7. **Les tests passent, là où ils sont le plus révélateurs** — sur une machine de test dès
   qu'elle peut révéler davantage que le local. C'est ce qui rend la tâche terminée.

## Outils de l'agent

| Fonction | Déclencheur | Ici |
|---|---|---|
| Doc à jour d'une bibliothèque | avant d'écrire du code qui utilise FastAPI, Pydantic, asyncpg, TanStack Query, Vite, i18next… | Context7 (MCP) |
| Contrat réel d'une CLI | avant tout appel à une CLI externe | `--help` d'abord — le binaire installé fait foi |
| Navigation sémantique | avant un refactor, pour trouver les usages | pas de Serena ici : Grep/Glob, ou sous-agent Explore |
| Méthodes de travail | plan, exécution, débogage, TDD | skills Superpowers déclarés (`skills-lock.json`) mais **non installés** dans ce workspace : suivre le cycle de l'architecte et la discipline de tests de ce fichier |
| Revue et commit | >3 fichiers ou >100 lignes | `/code-review` ; commit à la main, au format ci-dessus |

## Tchat agents
Le tchat (outils `tchat_*`) est le canal de COORDINATION multi-agents ; l'information reste dans
docflow. **En début de session, avant de rendre la main la première fois** : inscris-toi avec
`agent_register(session=<ta session tmux>, command=<ce qui t'a lancé>)`, puis appelle
`tchat_get_conversations` — et rappelle-le avant chaque fin de tour. À la vue du marqueur
`[TCHAT] nouveau message` dans ton stdin : `tchat_get_conversations` puis
`tchat_get_conversation`. Jamais de polling. Ton périmètre : page docflow
« Périmètre — ce que fait ragflow » (docflow://doc/c2144c01-7177-4537-bdd6-a848b6898e74),
à pousser en lien.
**Avant d'appeler, d'inviter ou de répondre à un agent, lis `ia_instructions/30_tchat.md`**
(texte intégral).

## Auto-amélioration
Quand tu fais une erreur ou que l'utilisateur te corrige :
- Ajoute une leçon dans `LESSONS.md`.
- Format : `- [module] description courte de l'erreur et de la bonne pratique`.
- Relis `LESSONS.md` en début de tâche qui touche un module mentionné.
- Ne dépasse pas 50 lignes — consolide les leçons similaires.

## Notifications de capacités
Quand tu invoques une capacité outillée (skill, commande, extension), affiche systématiquement
un marqueur **avant** d'exécuter :
> **`🟢 SKILL`** → _nom_ — raison en une phrase
