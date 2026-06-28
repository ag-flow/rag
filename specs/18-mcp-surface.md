# 18 — Surface MCP (outils déterministes)

> **Disclaimer.** Écrite à partir du serveur MCP réel (`api/mcp_standard.py`, FastMCP `@_mcp.tool()`), du registre `indexed_documents` (migration 003_jobs) et du constat que **seuls des chunks** sont stockés (`sections` + `embeddings`), **pas les fichiers d'origine**. Avant d'implémenter, **réévalue les impacts** et **revérifie** : couverture réelle des `sections` vs fichier, perfs du regex Postgres, état de sync exploitable. **Context7** (FastMCP / asyncpg), **Serena**, skill **`brainstorming`**. La décision ouverte (stocker ou non les originaux) est le vrai arbitrage — donne le minimum de contexte pour trancher.

## Rôle

Compléter la recherche **sémantique** (`rag_search`, enrichie en `16`/`17`) par des outils **déterministes**, pour que le rag soit une source de contexte **autosuffisante** — surtout pour un agent **sans disque** (Claude Web via le portail), qui sinon retombe sur du grep local qu'il n'a pas. Un agent dans un conteneur devpod a déjà ses outils natifs ; **la valeur est maximale pour le cas distant** — donc pour ton north star de cadrage.

**Discipline (garde-fou).** Trop d'outils MCP **dégradent** l'agent. On vise un **petit jeu orthogonal**, aux rôles non recouvrants :

| Outil | Rôle | Statut |
|---|---|---|
| `rag_search` | sémantique / hybride (16) + couches d'enrichissement (17) | existe, étendu |
| `search_files` | littéral exact / regex | **nouveau** |
| `get_document` | lecture du contenu indexé d'un path | **nouveau** (décision ci-dessous) |
| `index_status` | fraîcheur / couverture | **nouveau** |

`reindex` **n'est pas** un outil agent → reste côté API admin (action, pas contexte). On résiste à tout 5ᵉ outil flou.

## Dépendances (build order)

Construit **après** `16` et `17`, ce qui satisfait deux dépendances réelles :
- **`16` (soft)** : `search_files` mode exact-token s'appuie sur `content_tsv`. Sans `16`, plancher universel en `ILIKE` (sous-chaîne, sans tokenisation) — documenté.
- **`17`-C1** : `search_files`/`get_document` n'affichent le `source_path` réel (au lieu de `path::key`) que si la metadata des chunks le porte. Sans `17`, comportement dégradé : path synthétique `::key` retourné **tel quel, signalé comme enrichissement**.
- **`_WsCtx` à étendre** : il ne contient aujourd'hui ni `workspace_id` (UUID) ni `config_pool` — or `index_status`/le flag confidentialité interrogent la **DB config** (`indexed_documents`, `workspace_sources`, `index_jobs`, `workspaces`). `_load_context` les a déjà → les injecter dans `_WsCtx`.

## Outil 1 — `index_status` (le gain net, trivial)

Lecture seule, agrégée sur la **DB config**. Répond à une question de **confiance** : *« ce que je lis reflète-t-il l'état courant ? »* — aujourd'hui indiscernable.

```
index_status()              → { workspace, documents_count, last_indexed_at,
                                 sync: { last_indexed_at, next_sync_at,
                                         last_job_status, last_job_finished_at, healthy } }
index_status(path="…")      → { path, content_hash, indexed_at, indexer_used, title }
```

Dérivations exactes (schéma réel) :
- `documents_count` = `COUNT(*)`, `last_indexed_at` = `MAX(indexed_at)` sur `indexed_documents` filtré `workspace_id` (agrégats, **pas** de champ stocké).
- bloc `sync` : `last_indexed_at`/`next_sync_at` depuis `workspace_sources` ; `last_job_status`/`last_job_finished_at`/erreur depuis le **dernier** `index_jobs` (`ORDER BY finished_at DESC NULLS LAST`, index existant).
- `healthy` = dernier `index_jobs.status != 'error'` (règle simple et défendable ; affiner « pas d'erreur depuis N h » seulement si besoin).
- **`cursor` n'existe pas** en `18` — c'est le concept de l'interface Source (`19`). Il sera ajouté au bloc `sync` à ce moment-là, pas avant.

Aucun stockage nouveau, aucune migration. **Plus haute valeur/effort** des trois.

## Outil 2 — `search_files` (littéral, exact / regex)

Le complément déterministe du sémantique : *« trouve **toutes** les occurrences de `RAG_MASTER_KEY` »* — réponse **exhaustive**, pas « les 5 plus proches ».

**Nuance réelle à assumer** : le rag n'a **pas** les fichiers sur disque → ce n'est **pas** ripgrep. C'est une recherche **sur le contenu indexé** (`embeddings.content`, et `sections.content` pour le parent), avec trois modes explicites :
- **exact-token** : via `content_tsv` (`16`, sans stemming en `simple` → identifiants préservés). **Si `16` absent** → repli `ILIKE` (sous-chaîne, sémantique différente : ni token, ni casse/accents gérés) — documenté.
- **sous-chaîne** : `ILIKE '%motif%'` (toujours disponible).
- **regex** : opérateur Postgres `~` (seq scan sur `content` — acceptable sur corpus borné, **flag perf** si gros workspace ; pas d'index regex).
- Résultat : `path` (+ `source_path` réel si enrichissement et `17` livré, sinon `::key` signalé) + extrait + position chunk. Dédup vers `path`.

C'est le bras « mots exacts » côté outil, là où `rag_search` est le bras « sens ».

## Outil 3 — `get_document` (le point de décision)

**Constat qui change tout** : il n'existe **aucun fichier d'origine** stocké — seulement des chunks. Donc `get_file(path, lignes 120–148)` **fidèle n'est pas faisable** en l'état. Deux voies :

| Option | Ce qu'on sert | Coût | Fidélité |
|---|---|---|---|
| **A — reconstruire depuis `sections`** (reco V1) | contenu indexé d'un path = `sections.content` ordonnées ; granularité **section** (pas ligne) | **zéro stockage** | **fidèle prose/markdown/data** ; **approximatif code** (tree-sitter niche/élide → pas une reconstruction littérale ligne-à-ligne) |
| **B — stocker le contenu original** | vraie plage de **lignes** + regex `search_files` avec n° de ligne | **+~1× corpus** (texte, compresse bien) + write à l'indexation + **surface de confidentialité accrue** | fidèle partout |

**Reco : démarrer en A**, `get_document(path)` qui renvoie le contenu indexé reconstruit (fidèle pour la prose ; pour le **code**, renvoyer vers la chunk-viz `15` / les unités symboliques, et **documenter** l'approximation — ne pas faire croire à une copie littérale). Garder **B comme upgrade** si un besoin **concret** de plage-ligne-fidèle émerge (même logique que tsvector→BM25 en `16` : pas de stockage par anticipation). Décision à confirmer.

**Deux trous réels de l'option A à boucher :**
- **Ordre des sections.** `sections` n'a **pas** de colonne d'ordre : un `ORDER BY id` = ordre d'**insertion**, qui devient **faux** si un doc est refactoré (sections réordonnées, `id` inchangé via `ON CONFLICT DO UPDATE`). Correctif propre : ajouter `section_index INT` (ordre **déclaré** au chunking) → **petite migration workspace**. C'est aussi utile à la chunk-viz (`15`). Alternative (accepter l'ordre d'insertion + documenter) écartée : c'est un bug de correction silencieux, pas une simplification.
- **Workspaces legacy** (`engine=legacy`) : **aucune** ligne dans `sections` (uniquement `embeddings` à `section_id NULL`). Reconstruction via `sections` → vide. **Fallback** : reconstruire depuis `embeddings.content ORDER BY chunk_index` pour ces workspaces.

**`section_range` retiré de la V1** : format non défini, et inutile sans plage-ligne. `get_document(path)` renvoie le document indexé entier. Une sélection par `section_key` pourra être réintroduite plus tard avec un contrat défini.

## Confidentialité (`get_document` / `search_files`)

Servir du **contenu entier** est une surface plus large que des snippets de recherche. Donc :
- même `fail closed` + scope workspace + clé que `rag_search` (jamais cross-workspace) ;
- **flag par workspace** `allow_full_read BOOLEAN DEFAULT TRUE` sur la table `workspaces` (DB config) → un workspace peut être *cherchable* sans être *lisible en entier* (`get_document` refusé proprement si `false`). C'est une **migration** (cf. ci-dessous). `search_files` ne rend que des snippets → pas soumis au flag par défaut (à rediscuter si besoin).

## MCP

Trois nouveaux `@_mcp.tool()` (FastMCP, comme `rag_search`), chacun via `_ws_ctx` **étendu** (`workspace_id` + `config_pool`) + `fail closed`. Schémas d'outils auto-générés par le décorateur. La trace de débug (`16`) ne concerne que `rag_search` — `search_files`/`get_document` renvoient du déterministe sans trace.

## Migrations

L'affirmation « zéro migration » était **fausse** — il en faut deux, minimes et additives :
- **Config** : `ALTER TABLE workspaces ADD COLUMN allow_full_read BOOLEAN NOT NULL DEFAULT TRUE` (flag confidentialité).
- **Workspace** : `ALTER TABLE sections ADD COLUMN section_index INT` (ordre déclaré, pour `get_document` correct + chunk-viz `15`). Backfill des sections existantes par `id` croissant (ordre d'insertion = meilleure approximation disponible au backfill).
- Numéros indicatifs (à caler à l'implémentation selon l'ordre réel) : config après `16` (≈ `049`), workspace après `16` (≈ `004`).

## Tâches (TDD)

- [ ] Étendre `_WsCtx` (`workspace_id: UUID`, `config_pool`) — injectés depuis `_load_context`.
- [ ] `index_status()` + `index_status(path)` : agrégats `indexed_documents` + bloc sync (`workspace_sources` + dernier `index_jobs`, `healthy` = dernier job ≠ `error`). Lecture seule.
- [ ] `search_files(pattern, mode=exact|substring|regex, top_k)` : exact via `content_tsv` (`16`, repli ILIKE si absent), substring ILIKE, regex `~`. Dédup path, scope workspace.
- [ ] Migration workspace `sections.section_index` + backfill par `id` ; chunkers renseignent l'ordre déclaré.
- [ ] `get_document(path)` : reconstruction `sections ORDER BY section_index` ; **fallback legacy** `embeddings ORDER BY chunk_index` ; approximation code **documentée**.
- [ ] Migration config `workspaces.allow_full_read` ; `get_document` refuse proprement si `false`.
- [ ] 3 outils `@_mcp.tool()` + `_ws_ctx` étendu + `fail closed` ; tests de non-fuite cross-workspace.
- [ ] `source_path` réel affiché si `17` livré ; sinon path `::key` signalé comme enrichissement.
- [ ] Context7 (FastMCP) avant code.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts.
2. Les 3 outils sont **lecture seule**, scope workspace vérifié (`fail closed`, test cross-workspace négatif), requêtes paramétrées.
3. `get_document` désactivé sur un workspace flaggé sensible → refus propre.
4. Context7 consulté.

### Critères fonctionnels
5. `index_status()` renvoie `documents_count`/`last_indexed_at` (agrégats) et un bloc `sync` dérivé de `workspace_sources` + dernier `index_jobs` (`healthy` = dernier job ≠ `error`) ; `index_status(path)` le hash et la fraîcheur d'un doc.
6. `search_files("RAG_MASTER_KEY")` renvoie **toutes** les occurrences (exhaustif), avec `path`/`source_path` ; les modes exact/substring/regex fonctionnent.
7. `get_document(path)` reconstruit un doc prose **fidèlement** (sections ordonnées par `section_index`) ; un workspace **legacy** passe par le fallback `embeddings` ; sur du code, la réponse **signale** qu'elle est structurée par sections (pas littérale).
8. Le jeu d'outils reste **orthogonal** (4 outils) ; `reindex` non exposé ; `get_document` refusé proprement sur un workspace `allow_full_read=false`.

### Scénario de manipulation (recette de démonstration)
Depuis une session **Claude Web** (sans disque) sur le workspace `ag-flow-docker` :

1. `index_status()` → « 142 docs, dernière indexation il y a 12 min, sync OK ». L'agent **sait** qu'il lit du frais.
2. `search_files("RAG_MASTER_KEY")` → **toutes** les occurrences listées (là où `rag_search` n'en aurait remonté que les plus « proches »).
3. Sur un hit, `get_document("docs/auth.md")` → le contenu du doc reconstruit, lisible en entier sans avoir le repo monté.
4. Tenter `get_document` sur un workspace `colis21` flaggé sensible → refus propre (cherchable, pas lisible en entier).
5. Sur un fichier `.py`, `get_document` indique que le rendu est **structuré par symboles** et renvoie vers l'onglet Chunks (`15`) pour le détail.

**Ce que ça apporte.** Le rag devient **autosuffisant** pour un agent distant : il sait si l'index est frais (`index_status`), trouve une chaîne exacte de façon exhaustive (`search_files`), et lit un document sans disque (`get_document`). On complète le sémantique par du déterministe — sans prétendre servir ce qu'on n'a pas (les lignes brutes du fichier), honnêtement borné, et sans exposer plus que nécessaire (flag confidentialité).

## Notes / décisions ouvertes

- **Option A vs B de `get_document`** — *la* décision. Reco : A (reconstruit, +1 micro-migration `section_index`), B (stockage des originaux → plage-ligne fidèle) en upgrade sur besoin concret. À confirmer.
- **`section_index`** : retenu (correction d'ordre) plutôt qu'accepter l'ordre d'insertion — petit, additif, sert aussi `15`.
- **Dépendances déclarées** : `16` (soft, `content_tsv` ; sinon ILIKE), `17`-C1 (`source_path` ; sinon `::key` signalé). Build order les satisfait.
- **`healthy`** : règle V1 = dernier `index_jobs` ≠ `error`. Affiner (« pas d'erreur depuis N h ») seulement si un cas le justifie.
- **Perf regex** `~` : seq scan acceptable sur corpus borné ; restreindre à l'exact (tsvector) si un workspace grossit. À mesurer (harness `20`).
- **Flag `search_files`** : snippets = surface moindre → non soumis à `allow_full_read` par défaut ; à rediscuter pour corpus ultra-sensibles.
- **`cursor`** dans `index_status.sync` : ajouté en `19` (concept de l'interface Source), pas avant.
