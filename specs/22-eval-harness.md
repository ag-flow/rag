# 22 — Harness d'évaluation du retrieval

> **Disclaimer.** Instrument de mesure, **pas une feature** consommée par les agents — et la consigne première est la **minimalité** : mine-from-git + 3 métriques + table de comparaison, **pas une plateforme d'éval**. Avant d'implémenter, **revérifie** : l'accès au `git log` depuis le checkout (`repo_storage.path_for`), la signature du pipeline `services/mcp.py::search`, le format de hit (`path`/`source_path`). **Context7**, **Serena**, skill **`brainstorming`**. Résister à la sur-ingénierie est ici un **critère de réussite**.

## Position dans la série

Dernier de la série acquise. Ne s'utilise pas en runtime : il **pilote les réglages** de tout le reste. Sa valeur est indirecte mais réelle — sans lui, on règle à l'intuition, et plus on ajoute de boutons (chunking, hybride `16`, rerank, providers), **moins l'intuition suit**.

## Rôle

Mesurer **objectivement** la qualité de retrieval pour **décider** des réglages au lieu de les deviner. Le service a un espace de configuration énorme (stratégies de chunking, hybride on/off + `rrf_k`, 3 rerankers, N providers) ; le harness donne un **nombre par config** → on compare, on tranche.

## Comment ça marche, concrètement (le mécanisme en un exemple)

Pour dire qu'un réglage est « meilleur », il faut des questions **dont on connaît déjà la bonne réponse**. Sinon, un chunk remonté est impossible à juger. Tout le harness repose là-dessus — et le mining git fabrique ces couples *(question, bonne réponse)* gratuitement. Déroulé complet :

**1. Un commit → un cas.** Soit un commit réel :
```
"fix hash dedup race condition"   →  fichier modifié : dedup.py
```
Le **message devient la question**, le **fichier modifié devient la réponse attendue** :
`{ query: "fix hash dedup race condition", expected: ["dedup.py"] }`. Logique : qui a écrit ce message *cherchait* ce fichier → une bonne recherche, interrogée avec ce message, **doit** le ramener.

**2. On pose la question au rag, config A (vectoriel seul).** Il rend 5 résultats classés :
```
1. cache.py    ❌      2. dedup.py ✅   3. hasher.py ❌   4. config.py ❌   5. store.py ❌
```
On **note ce classement** — c'est tout ce que sont les métriques :
- **recall@5** = le bon est-il dans les 5 ? → oui → **1**
- **MRR** = à quelle position ? → position 2 → **1/2 = 0,5** (position 1 aurait donné 1)
- **nDCG** = même esprit, en plus fin (récompense d'être haut).

**3. Même question, config B (hybride + rerank).** Le classement change :
```
1. dedup.py ✅    2. hasher.py ❌    3. cache.py ❌    …
```
→ recall@5 = **1** · MRR = 1/1 = **1,0** (le bon est passé de la position 2 à la 1).

**4. On répète sur ~300 cas et on moyenne.** « B meilleur que A » cesse d'être une intuition :

| | recall@5 | MRR |
|---|---|---|
| A — vectoriel | 0,71 | 0,58 |
| B — hybride+rerank | 0,89 | 0,74 |

Sur 300 questions dont on connaissait déjà la réponse, B la trouve plus souvent (recall) et la classe plus haut (MRR). **C'est tout le mécanisme.**

**Le seul détail technique** : comment le programme sait qu'un résultat « est » `dedup.py` ? Chaque hit porte son `path` ; le cas attendait `dedup.py` ; on **compare les `path`**. Match → la position donne le score. Pas de magie : une comparaison de chaînes + un peu d'arithmétique.

> En trois gestes : **fabriquer les couples (question, attendu) depuis git → poser chaque question et relever la position du bon fichier → moyenner**. Les sections suivantes précisent chacun de ces gestes.

## Le benchmark, miné depuis l'historique git (l'astuce qui le rend réaliste)

Pas d'annotation manuelle. On **mine `git log`** : un commit qui modifie `dedup.py` avec le message « fix hash dedup race » fournit un cas
`{ query: "fix hash dedup race", expected: ["dedup.py"] }`. Le **message = requête**, les **fichiers changés = cibles attendues**. Des **centaines de cas gratuits**, ancrés dans le repo.

**Filtrage qualité** (essentiel — sinon benchmark bruité) :
- ignorer les **merge commits** ;
- ignorer les commits **trop diffus** (> N fichiers — refactor massif, pas une intention ciblée) ;
- ignorer les messages **triviaux** (« wip », « typo », < M mots) ;
- garder les commits **focalisés** (1–quelques fichiers) au message **descriptif**.

**Caveat honnête** : le message de commit est un **proxy** de la requête agent, pas son exact équivalent. Le harness mesure « le retrieval retrouve-t-il le fichier que ce commit décrivait ». Excellent pour la **comparaison relative de configs** (le but) ; à ne pas surinterpréter en qualité **absolue**.

## Métriques (définitions précises)

Les trois classiques — l'exemple ci-dessus en donne l'intuition ; voici les définitions de référence :

- **recall@k** — une cible attendue est-elle dans le top-k ? (le rappel, que l'hybride `16` améliore)
- **MRR** — rang réciproque du premier hit correct (précision du haut de liste)
- **nDCG@k** — qualité du classement, pondérée par le rang

Match par **`path`** : un hit correspond si son `path` (ou `source_path` pour un enrichissement, cf. `17`) égale un path attendu. Calcul par requête, puis moyenne.

## Ce qu'il évalue : le pipeline complet, par config

Le harness appelle le **pipeline réel** (`services/mcp.py::search`) — pas seulement `vector_search` — pour refléter ce que voit un agent (retrieve + RRF `16` + rerank). On compare des **configurations** :

- **Boutons *query-time*** (hybride on/off, `rrf_k`, rerank on/off, `top_k`) : comparables **sans réindexer** → le harness les bascule à la volée. C'est là qu'il brille (cycle de réglage rapide).
- **Boutons *index-time*** (stratégie de chunking, provider d'embedding) : changent l'**index** → nécessitent une **réindexation** entre deux runs. Le harness tourne contre l'état indexé courant ; on réindexe puis on relance. Plus lourd — à assumer.

## Couplage avec la chunk-viz (`15`)

La métrique dit **que** ça rate ; la viz dit **pourquoi**. Le harness **liste les cas qui ratent** (requête + path attendu absent du top-k) ; un clic/lien ouvre la chunk-viz (`15`) sur ce path → on voit si le chunk était mal découpé. Les deux faces du débug de retrieval, enfin réunies.

## Sources non-git

Le mining git ne vaut que pour les workspaces à source git. Pour `folder`/REST (`20`/`21`), pas d'historique → le harness accepte un **benchmark fourni** (fichier `query → expected_paths[]`). V1 : **mining git** (gratuit) + **benchmark fourni** comme échappatoire générique.

## Forme (minimale) & exécution

- Une **commande backend / endpoint admin** (lecture seule sur l'index ; lit `git log` depuis le checkout). **Pas** un outil MCP agent.
- Sortie = **table de comparaison** des configs (recall@k / MRR / nDCG) + **liste des cas en échec**. Benchmark mis en cache (réutilisé entre configs).
- Petit ajout dans `git_ops` : `commit_history(dest, max_count)` → `(sha, message, changed_files)`.

## Migrations

- **Aucune** : lit `git log` + interroge l'index ; benchmark et résultats en **fichiers regénérables** (JSON). Une table `eval_runs` (historique des runs) est une extension **différée**, pas V1.

## Tâches (TDD)

- [ ] `commit_history(dest, max_count)` dans `git_ops` (sha, message, fichiers changés).
- [ ] Mineur de benchmark : `git log` → cas `{query, expected[]}` + **filtrage qualité** (merges, diffus, triviaux). Testable sur un repo fixture.
- [ ] Métriques recall@k / MRR / nDCG@k (pures, testées isolément) ; match par `path`/`source_path`.
- [ ] Runner : pour une liste de configs (query-time), exécute `search`, agrège → table + cas en échec. Benchmark caché.
- [ ] Benchmark **fourni** (fichier) pour sources non-git.
- [ ] Commande/endpoint admin (lecture seule) ; pas d'outil MCP.
- [ ] Context7 avant code.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; métriques vérifiées sur cas connus (vecteurs de test).
2. **Lecture seule** : aucune écriture sur l'index ni le repo (prouvé).
3. **Minimal** : mine-from-git + 3 métriques + table — aucune sur-structure (pas de plateforme, pas de table non justifiée).
4. Context7 consulté.

### Critères fonctionnels
5. Miner un workspace git produit des cas `{query, expected}` après filtrage (merges/diffus/triviaux exclus).
6. Lancer le harness en **vector-only** vs **hybride+rerank** produit une **table** recall@5 / MRR / nDCG comparant les deux, **sans réindexer** (boutons query-time).
7. Les **cas en échec** sont listés avec leur path attendu ; un benchmark **fourni** fonctionne pour un workspace non-git.
8. Un changement *index-time* (chunking) est évaluable après **réindexation** (coût assumé, documenté).

### Scénario de manipulation (recette de démonstration)
1. Sur un workspace git (`ag-flow-docker`), miner le benchmark → « 312 cas retenus (sur 1 480 commits, après filtrage) ».
2. Lancer le harness avec deux configs query-time : **A** vectoriel pur, **B** hybride+rerank → table :
   `A: recall@5=0.71 MRR=0.58` · `B: recall@5=0.89 MRR=0.74`. **Décision chiffrée** : l'hybride (`16`) gagne, on l'active.
3. Ouvrir la **liste des cas en échec** de A → repérer une requête « identifiant exact » que A ratait et B retrouve.
4. Sur un cas qui rate **même en B**, cliquer → la chunk-viz (`15`) montre que le fichier était coupé au milieu d'une fonction → piste de réglage chunking.
5. Réindexer avec une autre stratégie de chunking, relancer → comparer (bouton index-time).

**Ce que ça apporte.** On passe du **réglage à l'intuition** au **réglage à la mesure**. Chaque décision (hybride, rerank, chunking, provider) devient un **nombre comparé**, pas une croyance — et le benchmark est **gratuit** (miné du repo). C'est l'instrument qui valide *a posteriori* tous les sujets précédents (l'hybride `16` vaut-il le coup ? l'overlap `20` suffit-il ?) et qui guidera les réglages futurs. Avec la chunk-viz (`15`), la boucle de débug est complète : mesurer **que**, voir **pourquoi**.

## Notes / décisions ouvertes

- **Proxy commit→requête** : assumé ; bon pour le **relatif** (comparer des configs), prudent sur l'**absolu**. Documenté.
- **Seuils de filtrage** (N fichiers, M mots) : à calibrer sur un vrai repo ; exposer en paramètres.
- **query-time vs index-time** : le harness brille sur le query-time (sans réindex) ; l'index-time coûte une réindexation — ne pas le cacher.
- **`eval_runs` (historique)** : table d'historique des runs = extension future ; V1 reste en fichiers regénérables.
- **Benchmark fourni** : format simple `query → expected_paths[]` (JSON) — le contrat minimal pour les sources non-git.
- **Ne pas faire une cathédrale** : si le harness commence à ressembler à un produit, c'est qu'on a dépassé le scope. Mesurer pour décider, rien de plus.
