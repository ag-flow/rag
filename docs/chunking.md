# Chunking par type de fichier

> Référence de fonctionnement du découpage (chunking) structure-aware.
> Décision d'architecture : [`docs/adr/0001-chunking-structure-aware.md`](adr/0001-chunking-structure-aware.md).
> Code : `backend/src/rag/indexer/chunking/`.

Ce document explique **comment un fichier est découpé en chunks selon son
type**, depuis l'extension jusqu'à l'algorithme appliqué.

---

## 1. Deux moteurs derrière un flag

Le découpage est piloté par le flag `chunking_configs.engine` (par **workspace**) :

| `engine` | Pipeline | Comportement |
|---|---|---|
| `legacy` (défaut) | Découpe plate char-based | Une seule stratégie (`paragraph` ou `markdown`) appliquée à **tous** les fichiers, sans tenir compte du type. Code : `make_chunker` (`factory.py`). |
| `structured` | Routage par type → small-to-big | Stratégie **choisie selon le type de fichier**, bornes en tokens, breadcrumb injecté, dédup incrémentale par `chunk_hash`. Code : `make_structured_chunker` (`structured_factory.py`). |

Le défaut `legacy` garantit **aucun changement de comportement** tant qu'un
workspace n'a pas explicitement basculé. La bascule `legacy → structured`
**déclenche une réindexation complète** du workspace (le texte embeddé change,
les vecteurs ne sont plus comparables) — cf. §6.

Le reste de ce document décrit le moteur **`structured`**.

---

## 2. La chaîne de résolution

Pour chaque fichier, la stratégie est résolue dans cet ordre (code :
`resolution.py::resolve_strategy_name`) :

```
override d'appel  ─┐
                   ├─►  nom de stratégie  ──►  (algo, params)  ──►  chunker
extension ─► catégorie ─► stratégie ─┘
```

1. **Override explicite à l'appel** — `PushRequest.strategy` (champ optionnel de
   `POST /workspaces/{name}/index`) référence directement une stratégie nommée
   du catalogue. **Prime sur tout.**
2. **Routage par type** — `extension → catégorie → nom de stratégie`. C'est le
   cas nominal (le `path` est toujours présent, en sync git comme en push ad hoc).
3. **Défaut** — extension non mappée → catégorie `prose` → stratégie de la
   catégorie `prose`.

Une stratégie nommée porte un **algo** (`prose` / `markdown` / `table` / `code`
/ `data`) et des **params** (tailles cibles en tokens, profondeur de
breadcrumb…). C'est l'algo qui détermine la mécanique de découpe.

---

## 3. Cartographie par défaut (seeds globaux)

Seedée en base par la migration `040_chunking_routing.sql` (+ `042`, `043`).

### Extension → catégorie

| Catégorie | Extensions |
|---|---|
| `prose` | `.md` `.markdown` `.txt` `.rst` |
| `code` | `.py` `.ts` `.tsx` `.js` `.jsx` `.go` `.rs` `.java` `.c` `.h` `.cpp` `.hpp` `.sql` `.sh` `.rb` `.php` `.css` `.scss` |
| `table` | `.csv` `.tsv` |
| `data` | `.json` `.yaml` `.yml` `.toml` `.xml` `.ini` |
| _(non mappée)_ | → catégorie `prose` par défaut |

### Catégorie → stratégie → algo

| Catégorie | Stratégie nommée | Algo | Params clés (défaut) |
|---|---|---|---|
| `prose` | `markdown-deep` | `prose` | `child_target_tokens=384`, `floor=64`, `overlap=64`, `breadcrumb_depth=-1`, `heading_levels=[1,2]` |
| `code` | `code-aware` | `code` | `child_target_tokens=512`, `floor=64`, `overlap=64`, `breadcrumb_depth=-1` |
| `table` | `table` | `table` | `child_target_tokens=512`, `max_rows_per_chunk=50` |
| `data` | `data-structured` | `data` | `child_target_tokens=512`, `floor=64`, `overlap=0`, `breadcrumb_depth=-1` |

---

## 4. Comportement par algo

Tous les algos `structured` produisent un **`ChunkedDocument`** = des **parents**
(`ParentSection`, texte renvoyé au LLM) + des **enfants** (`ChildChunk`, texte
réellement embeddé). C'est le modèle **small-to-big** (ADR §2) : on embedde une
unité fine, on retourne la section englobante.

### `prose` / `markdown` — `MarkdownDeepChunker`

- Découpe par **titres** (`heading_levels`, défaut H1/H2). Le préambule avant le
  premier titre est une section de niveau 0.
- Parent = section entière sous un titre ; enfant = paragraphe + breadcrumb.
- **Fallback paragraphe** si le document n'a aucun titre.
- C'est aussi le **fallback universel** des algos `code`/`data` (cf. ci-dessous).

### `code` — `CodeChunker` (tree-sitter)

- Découpe **par symboles** via tree-sitter (`code_chunker.py`) : chaque
  fonction / méthode / classe devient une unité (parent).
- Les **classes** sont émises en deux temps : une « coquille » (corps des
  méthodes élidé, remplacé par `… <nom>`) **plus** une unité par méthode, dont
  le breadcrumb porte la portée (`Classe > méthode`).
- Le code module-level (imports, statements top-level) est coalescé en unités
  `(module)`.
- L'indentation est **préservée** au split (sémantique en code, contrairement à
  la prose).
- **Config curée** (découpe fine par genre de nœud) pour : `python`,
  `javascript`, `typescript`, `tsx`, `go`, `rust`, `java`, `c`, `cpp`. Les
  autres langages reconnus par tree-sitter (`ruby`, `php`, `sql`, `bash`,
  `css`, `scss`…) tournent en **mode générique** (tout nœud nommé = une unité).
- Tree-sitter étant **tolérant aux erreurs**, le découpage reste best-effort sur
  du code partiellement invalide.

### `data` — `DataChunker` (tree-sitter)

- Pour JSON / YAML / TOML : chaque **clé de premier niveau** devient une unité
  (parent), son nom servant de breadcrumb (`data_chunker.py`).
- À défaut de structure clé-valeur reconnue, le document entier devient une
  unité unique `(root)`. **Jamais** de char-split.

### `table` — `TableChunker`

- Conserve la **ligne d'en-tête**, découpe par **groupes de lignes**
  (`max_rows_per_chunk`). Chaque enfant = en-tête + N lignes ; parent = table
  entière. Jamais de char-split (corrige le déchiquetage des tables en prose).

---

## 5. Langage tree-sitter & fallback gracieux

Pour les algos `code` et `data`, `RealIndexer` déduit le langage tree-sitter
depuis l'extension (`languages.py::language_for_path`) et l'injecte dans le
factory. Le fallback est **gracieux** (`structured_factory.py`) :

```
algo code/data + langage absent ........→ prose (borné en tokens)
algo code/data + langage non supporté ..→ prose (UnsupportedLanguageError)
```

Conséquence concrète : un fichier `.ini` (catégorie `data`, mais **non mappé**
dans `languages.py`) est traité en `prose`. Idem pour tout langage que le
`tree-sitter-language-pack` ne fournit pas. **On ne char-split jamais sauvagement** :
le garde-fou tokens du normaliseur s'applique dans tous les cas.

---

## 6. Garanties transverses (tous algos `structured`)

Détails et justifications dans l'ADR 0001 (§3 à §5).

- **Bornes en tokens** — la source de vérité est `model_dimensions.max_input_tokens`
  (migration 039). Le plafond dur = `floor(0.8 × max_input_tokens)` ; tout chunk
  qui le dépasse après split lève une erreur typée (`EmbeddingChunkTooLarge`),
  **jamais** d'envoi silencieux. `child_target_tokens` est la taille **cible**
  de récupération, clampée sous le plafond.
- **Breadcrumb injecté** — le chemin hiérarchique (titres / portée de code /
  clé) est **préfixé au texte embeddé** (`breadcrumb_depth` : `-1` = chemin
  complet, `0` = désactivé, `N>0` = N derniers niveaux).
- **Small-to-big** — récupération sur les enfants → dédup par `section_id` →
  renvoi du parent (`sections.content`).
- **Réindexation incrémentale** — identité d'un chunk = `(path, chunk_hash)` où
  `chunk_hash = sha256(texte exact embeddé, breadcrumb inclus)`. Un diff
  ensembliste ne ré-embedde que les chunks **réellement modifiés**.

**Bascule de moteur** = job de réindexation complète du workspace (purge des
sections orphelines incluse). Après bascule, les éditions suivantes sont
incrémentales.

---

## 7. Personnaliser le routage

Chaque objet de config existe en **défaut global** (`workspace_id IS NULL`) et
en **surcharge par workspace** ; la résolution effective fusionne global puis
workspace, **clé par clé** (`resolution.py::merge_maps`). Trois leviers :

| Pour changer… | Table |
|---|---|
| l'algo / les params d'une stratégie | `chunking_strategies` |
| la catégorie d'une extension | `chunking_extension_categories` |
| la stratégie d'une catégorie | `chunking_category_strategies` |

Pour un découpage ponctuel hors routage, passer `strategy: "<nom>"` dans le
corps de `POST /workspaces/{name}/index` (override d'appel, §2).

---

## 8. Récapitulatif des fichiers

| Fichier | Rôle |
|---|---|
| `resolution.py` | Résolution `override / extension → catégorie → stratégie` |
| `structured_factory.py` | `(algo, params) → chunker`, clamp tokens, fallback prose |
| `languages.py` | `extension → langage tree-sitter` |
| `markdown_deep.py` | Algo `prose` / `markdown` |
| `code_chunker.py` + `code_parser.py` | Algo `code` (tree-sitter) |
| `data_chunker.py` | Algo `data` (tree-sitter) |
| `table.py` | Algo `table` |
| `normalizer.py` + `tokens.py` | Bornes tokens (floor / ceiling / overlap) |
| `breadcrumb.py` | Préfixe de breadcrumb |
| `hashing.py` | `chunk_hash` pour le diff incrémental |
| `indexer/real.py` | Sélection du moteur + câblage du pipeline |
| `migrations/039,040,041,042,043` | Schéma + seeds de routage |
| `db/workspace_migrations/versions/002_*` | `sections` + `chunk_hash` (base workspace) |
