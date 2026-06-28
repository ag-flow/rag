# 16 — Recherche hybride (vectoriel + lexical + RRF)

> **Disclaimer.** Écrite à partir du retrieval réel (`db/workspace_search.py`, `services/mcp.py`, schéma `embeddings`/`sections`). Avant d'implémenter, **réévalue les impacts** et **revérifie les hypothèses** (signature de `vector_search`, point d'insertion du rerank, parser tsvector disponible). Utilise **Context7** (pgvector / FTS Postgres / ParadeDB le cas échéant), **Serena** pour naviguer le pipeline, le skill **`brainstorming`** avant d'écrire. Sur la **décision ouverte** (tsvector natif vs BM25), donne le minimum de contexte pour trancher — c'est le seul vrai arbitrage de cette spec.

## Rôle

Combler le **trou de rappel** de la recherche purement vectorielle. L'embedding capture le *sens*, pas les *chaînes littérales* : un agent qui cherche `HarpocrateClient`, `RAG_MASTER_KEY`, `${vault://…}`, un code d'erreur ou un chemin exact n'est pas garanti d'avoir le chunk porteur du token dans ses voisins cosinus. Le lexical (FTS) couvre exactement ce cas ; le vectoriel couvre les requêtes conceptuelles. **Modes d'échec complémentaires** → on fusionne les deux classements (Reciprocal Rank Fusion).

**Le point qui justifie la spec (et qu'on ne peut pas régler autrement).** Le rerank M8 ne réordonne que ce que le retrieval a **déjà** remonté. Si le chunk au token exact n'est jamais entré dans le vivier de candidats, le reranker ne peut pas le rattraper. L'hybride agit sur le **rappel** (ce qui entre dans le vivier), le rerank sur la **précision** (l'ordre du vivier). Complémentaires, pas redondants.

**Aigu pour les corpus de code** — précisément le profil dominant ici.

## Principe : un bras lexical en parallèle, fusionné en amont du rerank

```
              ┌─ bras vectoriel  (e.embedding <=> q)         ─┐
   requête ───┤                                                ├─ RRF (sur enfants)
              └─ bras lexical    (e.content @@ to_tsquery(q)) ─┘
                                                                │
                                       dédup small-to-big (parent, meilleur score fusionné)
                                                                │
                                       rerank M8 existant (opt-in)  →  top_k
```

Les **deux bras cherchent sur les mêmes enfants** (`embeddings.content`) → la fusion est homogène (même granularité), et la dédup small-to-big vers le parent (`sections.content`) s'applique **après** fusion, exactement comme aujourd'hui. Le rerank reste en bout de chaîne, inchangé.

## Le bras lexical

Index FTS sur `embeddings.content`, à la même granularité que le vectoriel. Deux implémentations possibles — **c'est la décision à trancher** :

| Option | Avantages | Coûts |
|---|---|---|
| **`tsvector` natif + GIN** (recommandé pour démarrer) | Intégré à Postgres, **zéro dépendance**, **colonne générée auto-maintenue** (aucun code de synchro), fonctionne sur **toute** base workspace sans provisioning | Ranking `ts_rank` faible *en absolu* ; parser `simple` découpe sur la ponctuation (`user.getById` → `user`,`getById`) |
| **ParadeDB / `pg_search` (BM25)** | Vrai **BM25 code-aware**, meilleur ranking lexical brut | **Extension à provisionner sur chaque DB workspace** (créées dynamiquement) → friction opérationnelle réelle |

**Recommandation : démarrer en `tsvector` natif.** Raison non triviale — dans un montage *hybride*, le job du bras lexical est le **rappel** (faire entrer le chunk au token exact dans le vivier), **pas le ranking final** : c'est le RRF puis le rerank qui ordonnent. Le point faible de `ts_rank` (ranking médiocre) est donc largement **masqué**. On garde BM25 comme **upgrade conditionnel**, décidé objectivement par le harness (`20`) si la mesure montre que le ranking lexical pèse. C'est la voie propre qui n'alourdit pas le provisioning par anticipation.

Colonne générée (auto-synchro avec `content`, aucune dérive possible) :

```sql
-- workspace migration 003
ALTER TABLE embeddings
  ADD COLUMN content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
CREATE INDEX embeddings_content_tsv ON embeddings USING GIN (content_tsv);
```

`simple` (sans stemming) par défaut : on **ne stemme pas** les identifiants de code (`getUserById` reste entier). Une config FTS par langue de workspace est une option (pour la prose), pas le défaut.

## Fusion RRF

Chaque bras produit une liste classée d'enfants. RRF fusionne par **rang** (robuste à la non-comparabilité des scores cosinus vs `ts_rank`) :

```
score_rrf(chunk) = Σ_bras  1 / (k + rang_bras(chunk))        k = 60 (défaut usuel)
```

- Identité de fusion = l'enfant (`path` + `chunk_hash`, `chunk_index` en repli legacy).
- Un chunk trouvé par **les deux** bras cumule les deux contributions → remonte (effet recherché).
- Après RRF : dédup small-to-big (parent, meilleur score RRF conservé), puis rerank existant, puis `top_k`. `min_score` s'applique sur le bras vectoriel comme aujourd'hui (le lexical n'a pas de seuil cosinus — filtré par le `@@` lui-même).

## Configuration — opt-in par workspace (cohérent avec le rerank)

Même philosophie que `rerank_configs` : **pas de row = comportement inchangé** (vectoriel pur). Un workspace active l'hybride explicitement.

```
-- global migration 048 : hybrid_configs
hybrid_configs(workspace_id PK→workspaces, enabled bool, rrf_k int DEFAULT 60,
               fts_config text DEFAULT 'simple')
```

Défaut **désactivé** à la livraison (additif, aucun workspace existant n'est modifié), activable par workspace via l'API admin. *(Si le harness montre l'hybride gagnant partout, on pourra discuter d'en faire le défaut — décision pilotée par la mesure, pas par principe.)*

## Impact playground — trace de débug (banc de test)

Le playground (`12`) n'est pas un chat de prod : c'est **le banc de test du RAG** (ses usages déclarés : « vérifier qu'un document est correctement indexé et retrouvable », « tester la qualité des chunks et des scores »). Avec l'hybride, un `score` unique ne suffit **plus** à expliquer un classement — il faut la **provenance**. Le pipeline expose donc une **trace de débug optionnelle**, demandée par le playground et **jamais par le `POST /mcp` agent** (les agents veulent des résultats propres ; le banc de test veut les internes).

Trace portée par chaque hit quand `debug=true` :

```
debug: {
  vector_rank, vector_score,    // bras vectoriel  (null si le chunk n'y figure pas)
  lexical_rank, lexical_score,  // bras lexical     (null si absent de ce bras)
  rrf_score,                    // score de fusion
  rerank_score,                 // null si pas de rerank sur le workspace
  final_rank                    // position finale après rerank + slice
}
```

- Flag `debug` au niveau du pipeline de recherche : **coût nul quand `false`** (aucune trace assemblée). Le playground le met toujours ; le `POST /mcp` ne l'expose jamais.
- `POST /workspaces/{name}/playground/chat` renvoie la trace dans le bloc `chunks` existant (champ `debug` par chunk).
- **IHM** : le panneau « Chunks utilisés » déplié montre, par chunk, **par quel(s) bras** il a été trouvé, son **rang** dans chacun, le **RRF**, et le **saut** opéré par le rerank — ex. *« lexical #1 · vectoriel hors-vivier → RRF → rerank → **final #1** »*. On voit *pourquoi* un résultat est là.

Complément de la chunk-viz (`15`) : `15` explique **comment un document a été découpé** ; la trace explique **pourquoi un résultat s'est classé là**. Les deux faces du débug de retrieval — et c'est précisément ce que le banc de test doit montrer.

## Migrations

- **Workspace 003** : colonne générée `content_tsv` + index GIN. Additive ; backfill automatique des lignes existantes (colonne `STORED`). Legacy (`chunk_hash NULL`) indexées aussi → l'hybride profite même aux corpus anciens.
- **Global 048** : table `hybrid_configs` (opt-in).

## Tâches (TDD)

- [ ] `lexical_search(workspace_pool, query, top_k_pre)` symétrique de `vector_search` (mêmes enfants, renvoie rang + identité).
- [ ] `rrf_fuse(vector_hits, lexical_hits, k)` → liste fusionnée d'enfants, testable isolément (cas : chunk dans 1 bras / dans les 2 / legacy).
- [ ] Brancher dans `services/mcp.py` **avant** le rerank ; respecter `top_k_pre_rerank` comme taille de vivier fusionné.
- [ ] Migrations 003 (workspace) + 048 (global) + endpoints admin `hybrid_configs` (GET/PUT).
- [ ] Multi-workspace : la fusion inter-workspace reste par score — vérifier la cohérence quand certains workspaces sont hybrides et d'autres non (cf. note).
- [ ] **Trace de débug** optionnelle (`debug=true`) portée par chaque hit le long du pipeline (vectoriel → lexical → RRF → rerank), **coût nul si `false`**.
- [ ] `playground/chat` met `debug=true` et renvoie la trace ; `POST /mcp` ne l'expose **jamais** (test de non-fuite).
- [ ] IHM playground : panneau « Chunks utilisés » enrichi (provenance par bras, rangs, RRF, saut rerank).
- [ ] Context7 (FTS Postgres) avant d'écrire les requêtes.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; migrations 003/048 appliquées sur l'env connecté.
2. **Comportement strictement inchangé** pour un workspace sans `hybrid_configs` (prouvé par test : mêmes résultats qu'avant).
3. Colonne `content_tsv` auto-maintenue (insert/update d'un chunk → tsvector à jour sans code applicatif).
4. RRF testé isolément ; Context7 consulté.

### Critères fonctionnels
5. Sur un workspace hybride, une requête à **identifiant exact** présent dans le corpus mais hors voisinage cosinus remonte le bon chunk (qu'elle ratait en vectoriel pur).
6. Une requête **conceptuelle** conserve au moins la qualité du vectoriel pur (le lexical ne dégrade pas).
7. La dédup small-to-big et le rerank existant fonctionnent identiquement sur le vivier fusionné.
8. Dans le **playground**, déplier un chunk montre sa **trace** (provenance par bras, rangs, RRF, score rerank, position finale) ; le `POST /mcp` ne renvoie **aucune** donnée de débug.

### Scénario de manipulation (recette de démonstration)
Le banc de test, c'est le **playground** — la recette s'y déroule :

1. Playground sur `ag-flow-docker`, hybride **désactivé**. Demander `RAG_MASTER_KEY` → déplier « Chunks utilisés » : le chunk porteur du token n'y est pas (trace : *vectoriel seul, le bon chunk est hors vivier*).
2. Activer l'hybride (`PUT /workspaces/ag-flow-docker/hybrid-config {enabled:true}`).
3. Rejouer `RAG_MASTER_KEY` → le chunk remonte **en tête** ; déplier → la trace montre *« lexical #1 · vectoriel hors-vivier → RRF → final #1 »*. On **voit** pourquoi.
4. Poser une requête conceptuelle (« comment la dédup évite de réembedder ») → réponse aussi bonne qu'avant ; trace : *le vectoriel domine*. Le lexical n'a pas dégradé.
5. Ouvrir l'onglet **Chunks** (`15`) sur le fichier remonté → confirmer que c'est bien le chunk au token exact.

**Ce que ça apporte.** On arrête de perdre **silencieusement** la moitié « identifiant exact » des requêtes — celle qu'un agent de code émet le plus. Le gain est sur le **rappel**, que ni le rerank ni un meilleur embedding ne pouvaient combler. Et le banc de test **montre la mécanique** (trace de provenance) au lieu d'un score opaque, donc on règle à la vue. Dette minimale : même Postgres, index auto-maintenu, en amont du rerank existant, opt-in sans toucher l'existant.

## Notes / décisions ouvertes

- **`tsvector` natif vs BM25 (ParadeDB)** — *la* décision. Reco : tsvector d'abord (rappel = job du bras lexical, ranking masqué par RRF+rerank ; zéro provisioning), BM25 en upgrade **gated par le harness** si la mesure le justifie. À confirmer par l'utilisateur.
- **Multi-workspace hétérogène** : si la requête couvre des workspaces hybrides + non-hybrides, la fusion inter-workspace finale reste par score. À cadrer : harmoniser (RRF aussi au niveau inter-workspace ?) ou laisser le rerank trancher. Lié à l'amélioration « fusion cross-workspace par rerank plutôt que cosinus brut » évoquée hors-liste.
- **`fts_config`** : `simple` (défaut, code-safe) vs config par langue (prose). Exposé en config workspace, défaut `simple`.
- **Poids vs RRF pur** : démarrer en RRF pur (pas de poids vecteur/lexical à régler). Introduire une pondération seulement si le harness montre un besoin — éviter un bouton de plus sans preuve.
