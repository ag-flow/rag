# Annexe technique — Pipeline de chunking

Ce document décrit le fonctionnement interne du découpage de documents (chunking)
tel qu'implémenté dans ag-flow.rag. Il est destiné aux intégrateurs et aux
opérateurs qui souhaitent comprendre comment les documents sont transformés avant
l'embedding.

---

## 1. Vue d'ensemble

Lorsqu'un document est soumis à l'indexation (via push API ou sync source), il
passe par un pipeline en trois étapes :

```
Document brut
     │
     ▼
[1] Découpage (chunking)
     │  → blocs logiques (prose, code, données)
     ▼
[2] Enrichissement (breadcrumb + normalisation)
     │  → textes bornés en tokens, prêts à l'embedding
     ▼
[3] Embedding + stockage
     │  → vecteurs en base, diff incrémental
     ▼
Index interrogeable
```

Deux moteurs coexistent, sélectionnables par workspace :

| Moteur | Clé config | Stratégie | Usage recommandé |
|---|---|---|---|
| `legacy` | `engine=legacy` | char-based, plat | Migration, compatibilité |
| `structured` | `engine=structured` | small-to-big, token-based | Défaut pour tout nouveau workspace |

---

## 2. Moteur legacy (char-based)

Le moteur legacy utilise deux stratégies basées sur le nombre de caractères.

### Stratégie `paragraph`

Algorithme en 4 étapes :

1. **Split** sur double saut de ligne (`\n\n`). Si un seul bloc dépasse
   `max_chars`, re-split sur saut de ligne simple.
2. **Coalesce** : les paragraphes inférieurs à `min_chars` sont fusionnés avec le
   suivant, tant que le total reste sous `max_chars`.
3. **Split des gros blocs** : ceux qui dépassent `max_chars` sont coupés sur la
   dernière frontière naturelle trouvée dans une fenêtre de 200 caractères avant
   la limite (`. ` → `\n` → ` `). En l'absence de frontière, coupure dure.
4. **Overlap** : chaque chunk (sauf le premier) est préfixé des `overlap_chars`
   derniers caractères du chunk précédent pour assurer la continuité sémantique.

Paramètres : `max_chars`, `min_chars`, `overlap_chars`.

### Stratégie `markdown`

Étend `paragraph` avec une conscience des titres Markdown :

1. **Sectionnement** : le document est découpé sur les titres H{n} dont le niveau
   appartient à `heading_levels` (défaut : H1 et H2). Chaque section embarque
   son titre et le chemin de ses ancêtres (`section_path`).
2. **Préambule** : le texte situé avant le premier titre devient une section
   `level=0` sans titre.
3. **Sub-split par section** : si une section dépasse `max_chars`, elle est
   re-découpée en préservant les blocs de code (fences ` ``` ` ou `~~~`) comme
   unités indivisibles. Le texte prose autour des fences repasse dans
   `paragraph`.
4. **Fallback** : si aucun titre aux niveaux configurés n'est trouvé, le document
   entier délègue à `ParagraphChunker`.

Chaque chunk produit embarque des métadonnées :
`section_title`, `section_path`, `heading_level`.

---

## 3. Moteur structured (small-to-big, token-based)

Le moteur `structured` est le moteur par défaut. Il introduit deux niveaux de
granularité : les **sections parentes** (texte brut renvoyé au LLM lors d'une
recherche) et les **enfants** (extraits normalisés, embeddés et stockés en base).

### 3.1 Routage par type de fichier

Avant tout découpage, le moteur détermine quelle stratégie appliquer au fichier :

```
extension de fichier
      │
      ▼ table chunking_extension_categories
   catégorie (ex: "prose", "code", "data", "table")
      │
      ▼ table chunking_category_strategies
   stratégie nommée (ex: "default-prose", "default-code")
      │
      ▼ table chunking_strategies
   algo + params (ex: algo="prose", child_target_tokens=384, ...)
```

Les tables globales définissent les défauts système. Une configuration
workspace surcharge clé par clé (extension ou catégorie) sans écraser le reste.
Un `strategy_override` passé au moment du push court-circuite le routage
automatique.

### 3.2 Algos disponibles

| Algo | Chunker | Mécanisme |
|---|---|---|
| `prose` / `markdown` | `MarkdownDeepChunker` | Sectionnement Markdown + normalisation en tokens |
| `code` | `CodeChunker` (tree-sitter) | Découpage par symboles (fonctions, classes, méthodes) |
| `data` | `DataChunker` (tree-sitter) | Découpage par clés de premier niveau (JSON, YAML, TOML) |
| `table` | `TableChunker` | Découpage par paquets de lignes (CSV, TSV) |

Si le langage tree-sitter n'est pas supporté pour `code` ou `data`, l'algo
bascule gracieusement vers `prose`.

### 3.3 Normalisation en tokens (`TokenNormalizer`)

Tous les blocs produits par les algos passent par le `TokenNormalizer` avant
l'embedding. Il applique deux passes successives :

**Passe 1 — Floor (fusion)** : les blocs dont l'estimation en tokens est
inférieure à `floor_tokens` sont fusionnés avec le bloc suivant, tant que le
résultat tient sous `child_target_tokens`. Les blocs atomiques (fences de code)
ne sont jamais fusionnés.

**Passe 2 — Ceiling (split)** : les blocs qui dépassent `child_target_tokens`
sont découpés mot par mot dans un budget `child_target_tokens − overlap_tokens`.
Si `overlap_tokens > 0`, chaque morceau (sauf le premier) est préfixé du suffixe
du morceau précédent afin d'atteindre `overlap_tokens` tokens de recouvrement.

**Plafond dur** : calculé comme `floor(safety_factor × provider_max_input_tokens)`
(défaut `safety_factor = 0.8`). Toute unité atomique dépassant ce plafond lève
une erreur explicite — jamais de troncature silencieuse.

**Estimation de tokens** : le `HeuristicTokenEstimator` estime `len(texte) ×
char_ratio`, où `char_ratio` est configurable par workspace (défaut déduit du
provider). L'estimation est intentionnellement conservative.

### 3.4 Algo `prose` — MarkdownDeepChunker

1. **Sectionnement** Markdown identique au moteur legacy (`split_into_sections`).
2. **Split des blocs** : chaque section est divisée en blocs logiques
   (`split_blocks`) : les fences de code deviennent des `Block(atomic=True)`,
   le reste est découpé sur ligne vide.
3. **Normalisation** : `TokenNormalizer` sur la liste de blocs de la section.
4. **Breadcrumb** : le chemin des ancêtres est préfixé au texte de chaque enfant
   avant l'embedding (`prepend_breadcrumb`). La profondeur est configurable
   (`breadcrumb_depth=-1` = chemin complet).
5. **Section parente** : le texte brut de la section (sans breadcrumb) est stocké
   séparément — c'est lui qui sera renvoyé au LLM quand un enfant matche.

### 3.5 Algo `code` — CodeChunker (tree-sitter)

Tree-sitter parse le fichier source en AST. Le chunker parcourt les nœuds de
premier niveau et construit des unités :

- **Fonctions / méthodes libres** → une unité par symbole, scope = `[nom]`.
- **Classes** → une unité « coquille » (corps des méthodes remplacé par un
  marqueur `… nom`) + une unité par méthode, scope = `[Classe, méthode]`.
- **Code module-level** (imports, statements, constantes) → coalescé en une ou
  plusieurs unités `(module)` sur ligne vide.

Chaque unité devient un `ParentSection`. Ses enfants sont les blocs du texte de
l'unité, passés dans `TokenNormalizer`, avec le scope comme breadcrumb.

Langages supportés avec configuration curée : Python, JavaScript, TypeScript,
TSX, Go, Rust, Java, C, C++. Les autres langages parsés par tree-sitter sont
traités en mode générique (tout nœud nommé = une unité).

### 3.6 Algo `data` — DataChunker (tree-sitter)

Tree-sitter parse le fichier de données (JSON, YAML, TOML). Le chunker remonte
les paires clé-valeur de premier niveau (`pair`, `block_mapping_pair`) et en fait
des unités indépendantes (scope = `[clé]`). Si aucune paire n'est détectée, le
document entier forme une seule unité.

### 3.7 Diff incrémental

À chaque réindexation, les enfants existants sont chargés par leur `chunk_hash`
(SHA-256 du texte d'embedding). Seuls les enfants dont le hash est absent de la
base sont envoyés au provider d'embedding et stockés. Les chunks inchangés sont
réutilisés tels quels — cela évite de consommer du quota d'embedding pour du
contenu stable.

---

## 4. Paramètres de configuration

| Paramètre | Algo | Défaut | Description |
|---|---|---|---|
| `child_target_tokens` | tous (structured) | 384 | Taille cible d'un enfant en tokens |
| `floor_tokens` | prose, code, data | 64 | Seuil de fusion (blocs en-dessous = fusionnés) |
| `overlap_tokens` | prose, code, data | 64 | Recouvrement entre enfants issus d'un même bloc |
| `breadcrumb_depth` | prose, code, data | -1 (complet) | Nombre de niveaux de contexte préfixés |
| `heading_levels` | prose | [1, 2] | Niveaux de titre qui délimitent les sections |
| `max_rows_per_chunk` | table | 50 | Nombre maximum de lignes par chunk |
| `max_chars` | legacy | configurable | Taille max d'un chunk en caractères |
| `min_chars` | legacy | configurable | Seuil de coalesce en caractères |
| `overlap_chars` | legacy | configurable | Recouvrement en caractères |

---

## 5. Garanties et invariants

- **Pas de troncature silencieuse** : une fence de code ou un token unique
  dépassant le plafond dur lève une erreur explicite (`ChunkTooLargeError`).
- **Déterminisme** : même contenu + même configuration → même découpage. Le diff
  incrémental repose sur cette propriété.
- **Préservation des fences** : les blocs ` ``` ` et `~~~` ne sont jamais
  fusionnés avec la prose voisine ni découpés à l'intérieur.
- **Fallback gracieux** : langage tree-sitter non supporté → bascule sur `prose`
  sans erreur.
- **Isolation workspace** : la configuration de routage et les stratégies nommées
  peuvent être surchargées par workspace sans affecter les autres.
