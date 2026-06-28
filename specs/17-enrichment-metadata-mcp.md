# 17 — Exposer la métadonnée d'enrichissement (MCP)

> **Disclaimer.** Écrite à partir de l'implémentation réelle de l'enrichissement (`services/enrichments.py`, table `document_enrichments` migration 031, `indexer/real.py::index_file`). Avant d'implémenter, **réévalue les impacts** et **revérifie les hypothèses** : le path synthétique `{path}::{metadata_key}`, l'absence de `metadata_key` dans `embeddings.metadata`, la signature de `index_file`. **Context7** (API), **Serena** (navigation), skill **`brainstorming`** avant d'écrire. Sur les décisions ouvertes (politique de mélange par défaut, exposition du résultat structuré), donne le minimum de contexte pour trancher.

## Rôle

**Monétiser un investissement déjà payé.** Les triggers (`13`) génèrent déjà, à l'indexation, des métadonnées nommées (`documentation`, `public_functions`, `dependencies`…) — appels LLM, stockage, embedding **déjà faits**. Mais la recherche les **noie** : elle ne sait pas dire « ceci est la liste des fonctions publiques de `dedup.py` », et l'agent ne peut ni les cibler ni les exclure. On a construit un différenciateur et on le cache. Ce sujet l'expose — il ne nous met pas *à parité*, il nous met **en avance** (rare dans le champ).

## État réel (le « à moitié construit »)

```
document_enrichments  (DB config — SOURCE DE VÉRITÉ)
   (workspace_id, path, template_id) UNIQUE
   metadata_key, result_type(text|json), result, result_schema, result_hash, llm_*

store vectoriel (par workspace)
   l'enrichissement est réindexé sous un PATH SYNTHÉTIQUE :  {path}::{metadata_key}
   → ex. embeddings.path = "src/dedup.py::public_functions"
   → MAIS embeddings.metadata ne porte PAS metadata_key (index_file n'injecte rien)
```

**Donc** : côté recherche, le seul signal qu'un chunk est un enrichissement est le **suffixe `::key` du path** — convention fragile, non contractuelle, et le `source_path` réel (`src/dedup.py`) est masqué par le suffixe. Le résultat **structuré** (`result_type=json`) n'est pas exploitable : seul son embedding texte remonte, jamais le JSON.

## Principe : faire de l'enrichissement une dimension first-class et contrôlable

Deux postures, par incrément — on **n'oblige jamais** l'agent à connaître la structure pour obtenir un résultat correct :

- **Implicite (gratuit, immédiat)** : chaque hit d'enrichissement est **étiqueté** (`enrichment_key` + `source_path` réel) au lieu du `path::key` confus. L'agent *voit* « ceci vient de `public_functions` de `src/dedup.py` » sans rien demander.
- **Explicite (puissant)** : l'agent peut **filtrer** (`enrichment_keys=[…]`), **exclure** (code brut seul) ou **récupérer le résultat canonique** structuré.

## Séquence de construction (C1 socle)

Ordre imposé par les dépendances (confirmé par audit du code) : **C1 → C2 → C3 → C4 → C5**. C1 est le **socle** : sans `extra_metadata` propagé jusqu'aux chunks **et** sans metadata retournée dans `SearchHit`, les changements 2/4/5 n'ont **rien à lire**.

## Changement 1 — porter `enrichment_key` + `source_path` sur les chunks

- Étendre `index_file` d'un paramètre optionnel `extra_metadata: Mapping` **fusionné** dans la `metadata` de chaque chunk/section produit (extension **générale**, utile au-delà de l'enrichissement). Aucune migration (JSONB existant dans `embeddings` **et** `sections`, confirmé).
  - Le paramètre est absent des **3 implémentations** du protocole — `protocol.py` (interface), `real.py`, `noop.py` — à propager dans les trois.
  - Les **3 chunkers** (`MarkdownDeepChunker`, `CodeChunker`, `DataChunker`) construisent déjà un dict `metadata` ; il suffit d'y **fusionner** l'`extra_metadata` reçu (ne pas écraser les clés du chunker : breadcrumb, bornes…).
- `run_enrichments` passe `extra_metadata={"enrichment_key": metadata_key, "source_path": path}` à `index_file`. Les **nouveaux** enrichissements portent la clé nativement.
- **Backfill one-shot** des enrichissements existants : commande de maintenance qui, pour chaque row de `document_enrichments`, met à jour la `metadata` des chunks au path synthétique correspondant (`UPDATE embeddings/sections SET metadata = metadata || jsonb …`). Piloté par la table de vérité (pas par parsing de `::`). Idempotent, documenté.

→ Le suffixe `::key` redevient un **détail interne** ; le contrat de recherche s'appuie sur la metadata, pas sur une convention de chaîne.

## Changement 2 — recherche : étiqueter, filtrer, scoper

- **Prérequis (étape 0)** : aujourd'hui `SearchHit` **ne retourne pas la metadata** — `workspace_search.py` ne la `SELECT` même pas. Avant tout étiquetage, faire **transiter la metadata** : ajouter `e.metadata` au `SELECT`, un champ `metadata` sur `SearchHit`. Sans ça, rien à étiqueter ni à filtrer. *(Bénéficie aussi à la chunk-viz `15` et à la trace `16`.)*
- **Étiquetage** : tout hit d'enrichissement renvoie `enrichment_key` + `source_path` réel (au lieu du path synthétique). Un hit brut renvoie `enrichment_key: null`.
- **Filtre** : `enrichment_keys: ["public_functions", …]` → ne retient que ces couches.
- **Périmètre** (`scope`) : `both` (défaut) | `raw_only` | `enriched_only`. Aujourd'hui les enrichissements sont **silencieusement mélangés** aux chunks bruts ; ce contrôle rend le mélange **choisi** — un agent qui veut le *code* exact peut exclure les synthèses, un agent qui veut *comprendre* peut ne lire que `documentation`.
- Défaut **`both` + étiqueté** : additif, **aucune régression** de comportement, gain immédiat de lisibilité.

## Changement 3 — `get_enrichment(path, key)` (lookup canonique)

Récupération **directe** du résultat depuis `document_enrichments` — le **résultat complet**, pas un chunk, et **structuré** si `result_type=json` (validé par `result_schema`). Pour « donne-moi *la* liste des fonctions publiques de `dedup.py` », c'est supérieur à un embedding texte fragmenté.

*(Spécifique à l'enrichissement → appartient à ce sujet. Le `get_file` générique, lui, reste au sujet surface MCP `18`. Frontière nette : `get_enrichment` lit `document_enrichments`, `get_file` lira des chunks bruts.)*

## Changement 4 — exposition MCP (le cœur du sujet)

L'outil `search` MCP gagne `enrichment_keys` + `scope` ; ses résultats portent `enrichment_key`/`source_path`. Un outil `get_enrichment` est ajouté. C'est ici que le différenciateur devient **consommable par Claude Web et les agents**.

## Changement 5 — playground (banc de test)

Réutilise la **trace de débug** (`16`) : le panneau « Chunks utilisés » étiquette chaque hit d'enrichissement par sa clé et son `source_path`, et un toggle `scope` (both/raw/enriched) permet de **voir l'effet** du filtrage. On teste le différenciateur à la vue.

## Synergie avec l'hybride (`16`)

Une fois les deux en place : router une requête « nom de fonction exact » vers le **lexical sur `enrichment_key=public_functions`**, une question conceptuelle vers le **vectoriel sur `documentation`**. Les deux sujets se renforcent — c'est pourquoi 16 précède 17.

## Migrations / backfill

- **Aucune migration structurelle** : `extra_metadata` utilise le JSONB existant.
- **Backfill** = commande de maintenance pilotée par `document_enrichments` (cross-DB config→workspace, donc Python, pas SQL pur). Les nouveaux enrichissements n'en ont pas besoin.

## Tâches (TDD) — ordre C1 → C2 → C3 → C4 → C5

- [ ] **C1** `index_file(..., extra_metadata=None)` propagé dans les **3 impls** (`protocol.py`, `real.py`, `noop.py`) ; les 3 chunkers **fusionnent** l'extra sans écraser leurs clés (test : metadata présente sur enfants **et** parents).
- [ ] **C1** `run_enrichments` injecte `{enrichment_key, source_path}` (remplace l'usage nu du path synthétique ligne ~88).
- [ ] **C1** Backfill : commande de maintenance, idempotente, pilotée par `document_enrichments`.
- [ ] **C2** Étape 0 : `SELECT e.metadata` + champ `metadata` sur `SearchHit` (la metadata n'est pas retournée aujourd'hui).
- [ ] **C2** Étiquetage `enrichment_key`/`source_path` + filtre `enrichment_keys` + `scope` (both/raw_only/enriched_only). Défaut `both`, comportement inchangé prouvé.
- [ ] **C3** `get_enrichment(workspace, path, key)` → résultat canonique (text ou json structuré).
- [ ] **C4** MCP : `rag_search` (aujourd'hui `query`/`top_k`/`min_score` seulement) gagne `enrichment_keys`,`scope` + résultats étiquetés ; nouvel outil `get_enrichment`. Scope workspace, `fail closed`.
- [ ] **C5** Playground : `ChunkResult` (aujourd'hui sans metadata) porte l'étiquette ; `PlaygroundChatTab` gagne le toggle `scope`.
- [ ] Context7 avant code.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; backfill exécuté sur l'env connecté.
2. `index_file` sans `extra_metadata` → comportement **strictement inchangé** (prouvé).
3. Recherche `scope=both` sans filtre → **mêmes résultats qu'avant** (additif, prouvé).
4. `get_enrichment` renvoie le `result` canonique ; si `json`, conforme à `result_schema`. Scope workspace vérifié.

### Critères fonctionnels
5. Un hit d'enrichissement remonte avec `enrichment_key` + `source_path` réel (plus le path synthétique).
6. `enrichment_keys=["public_functions"]` ne retourne que cette couche ; `scope=raw_only` exclut tous les enrichissements ; `enriched_only` ne garde qu'eux.
7. `get_enrichment("src/dedup.py","public_functions")` renvoie la liste **structurée** quand `result_type=json`.
8. Le `POST /mcp` expose les nouveaux champs/params ; un workspace **sans** triggers se comporte exactement comme avant (rien à étiqueter).

### Scénario de manipulation (recette de démonstration)
Dans le **playground** sur `ag-flow-docker` (triggers `.py` actifs) :

1. Demander « les fonctions publiques du module de déduplication ». La réponse s'appuie sur un hit **étiqueté `public_functions` · source `src/dedup.py`** (plus le `dedup.py::public_functions` cryptique).
2. Mettre `scope=raw_only` et rejouer → seuls les chunks de **code brut** remontent (les synthèses disparaissent). Inverse avec `enriched_only`.
3. Filtrer `enrichment_keys=["dependencies"]` sur « de quoi dépend ce module ? » → on cible directement la couche dépendances.
4. Appeler `get_enrichment("src/dedup.py","public_functions")` → la **liste structurée** complète (JSON), pas un fragment embeddé.
5. Côté débug : déplier un hit → voir l'étiquette d'enrichissement dans la trace (`16`).

**Ce que ça apporte.** Le RAG cesse de rendre « des bouts de fichiers » indifférenciés : il rend **la doc, ou les dépendances, ou le code — au choix**, et le résultat structuré quand il existe. On exploite enfin un enrichissement déjà payé, et on creuse un écart que peu de concurrents ont. Couplé à l'hybride, on route chaque requête vers la bonne couche par le bon bras.

## Notes / décisions ouvertes

- **Politique de mélange par défaut** : `both` + étiqueté (reco — additif, zéro régression). Alternative : `raw_only` par défaut (enrichissements opt-in) — plus conservateur mais cache le différenciateur. À trancher.
- **Résultat structuré dans la recherche** : faut-il que `search` puisse renvoyer le `result` JSON canonique (pas seulement le chunk) quand un hit est un enrichissement `json` ? Ou réserver ça à `get_enrichment` ? Reco : `get_enrichment` pour le structuré, `search` pour la pertinence — séparation nette.
- **Backfill** : one-shot piloté par `document_enrichments`. Décider s'il tourne en commande manuelle ou au démarrage (idempotent dans les deux cas).
- **`source_path` vs path synthétique dans les autres surfaces** (chunk-viz `15`, get_file `18`) : harmoniser l'affichage du `source_path` réel partout où un enrichissement apparaît.
