# Plan — Chunking Mermaid / diagrammes (Lots 1 → 3)

> Suite du chantier chunking structure-aware (ADR 0001). Traite le trou
> identifié : aucun traitement dédié des diagrammes Mermaid aujourd'hui.
> Brainstorm validé le 2026-06-24.

## Constat (mesuré, pas supposé)

Chemin actuel d'un Mermaid embarqué (fence ```` ```mermaid ```` dans un `.md`) :
catégorie `prose` → `MarkdownDeepChunker` → `split_blocks` (fence isolée comme
bloc) → `TokenNormalizer`. Trois comportements selon la taille :

- entre `floor` (64) et `child_target` (384) tok : **atomique** ✅
- `< floor` : `_merge_floor` colle la fence au paragraphe voisin ⚠️
- `> child_target` : `_split_ceiling` **word-shred** la fence (`block.split()`) ❌

La garantie « fence atomique » de `split_blocks` **ne survit pas au
`TokenNormalizer`** (qui voit une string opaque). Fichier `.mmd`/`.mermaid`
autonome : extension non mappée → `prose` → pire cas (split prose + word-shred).

## Outillage disponible (vérifié)

`tree-sitter-language-pack` fournit **`mermaid` et `dot`** (zéro nouvelle dépendance,
réutilise `CodeParser`/`CodeNode`). PlantUML absent. Fiabilité grammaire mesurée :

| Type | Parsing | Note |
|---|---|---|
| `sequenceDiagram` | ✅ propre | acteurs/signaux/texte |
| `erDiagram` (relations) | ✅ propre | corps `{…}` d'entité ⚠️ ERROR |
| `flowchart TD/LR` | ✅ propre | nœuds/liens/labels d'arête |
| **`graph TD`** | ❌ ERROR total | **rattrapé** par réécriture 1 ligne `graph→flowchart` (vérifié) |
| `classDiagram` | ⚠️ partiel | relations/méthodes ok, corps bruités |
| `stateDiagram-v2`, `pie` | ✅ parse | |

## Décisions de design (validées)

1. **Couverture v1** : trio curé **flowchart (+ rattrapage `graph`), erDiagram,
   sequenceDiagram** + **repli générique** sac-de-labels pour le reste.
2. **Séquencement** : **lot 1+2 complet d'abord**, puis lot 3 par-dessus.
3. **Projection** (lot 3) : parent = diagramme brut au LLM (inchangé) ; child
   embeddé = **projection en langage naturel** des relations. Une fois projeté en
   prose, le `TokenNormalizer` redevient approprié (on découpe de la vraie
   prose), donc le lot 3 ne souffre pas du problème d'atomicité.

---

## LOT 1 — Atomicité des fences respectée par le normaliseur

Objectif : un bloc marqué atomique n'est **ni mergé** (floor) **ni word-splitté**
(ceiling). S'il dépasse le plafond dur → `ChunkTooLargeError` (cohérent
ADR 0001 §3, jamais de troncature silencieuse). Sous le plafond mais au-dessus
de `child_target` → conservé entier (un child « gros mais acceptable »).

Callers de `TokenNormalizer.normalize` aujourd'hui : `markdown_deep`,
`code_chunker`, `data_chunker` (tous `list[str]`, tous non-atomiques sauf les
fences markdown).

### T1.1 — Type `Block` porteur du flag atomique
- **Rouge** : `tests/unit/indexer/test_normalizer.py` — `normalize` reçoit un
  `Block(text, atomic=True)` sous `floor` → **pas** mergé avec ses voisins.
- **Vert** : introduire `@dataclass(frozen=True) Block { text: str; atomic: bool }`
  dans `normalizer.py` (+ helper `Block.prose(t)`). `normalize` accepte
  `list[Block]` ; back-compat : conserver une surcharge `list[str]` → tous
  `atomic=False` (les 3 callers non touchés restent verts).

### T1.2 — Floor : l'atomique est une barrière
- **Rouge** : un bloc atomique minuscule entre deux paragraphes courts → 3
  children distincts (pas de fusion à travers l'atomique).
- **Vert** : `_merge_floor` ne bufferise jamais un bloc atomique et flush le
  buffer courant avant lui.

### T1.3 — Ceiling : l'atomique n'est jamais word-splitté
- **Rouge** : bloc atomique > `child_target` mais < `hard_ceiling` → 1 child
  entier. Bloc atomique > `hard_ceiling` → `ChunkTooLargeError`.
- **Vert** : `normalize` court-circuite `_split_ceiling` pour les atomiques ;
  garde-fou plafond dur explicite.

### T1.4 — Câblage `split_blocks` → fences atomiques
- **Rouge** : `tests/unit/indexer/test_chunking_markdown.py` — un `.md` avec une
  grosse fence ```` ```mermaid ```` (> 384 tok) produit **1** child contenant la
  fence entière (plus de fragments).
- **Vert** : `_sections.split_blocks` retourne `list[Block]` (fences → `atomic=True`,
  prose → `atomic=False`) ; `MarkdownDeepChunker.chunk` passe les `Block` tels quels.

### T1.5 — Doc
- Mettre à jour `docs/chunking.md` §4 (prose) + ADR 0001 : la garantie
  d'atomicité des fences est désormais de bout en bout.

---

## LOT 2 — Catégorie `diagram` + routage `.mmd`/`.mermaid`

Objectif : aligner le Mermaid autonome sur l'embarqué et donner une cible de
routage propre au lot 3. **À ce stade l'algo de la stratégie `diagram` reste
`prose`** (borné, atomique grâce au lot 1) — le tree-sitter arrive au lot 3,
exactement comme `code-aware` a été `prose` au Lot 1 puis `code` au Lot 2.

### T2.1 — Migration 044
- **Rouge** : `tests/integration/test_migration_044_diagram_category.py` — après
  migration : extension `.mmd`/`.mermaid` → catégorie `diagram` ; catégorie
  `diagram` → stratégie `mermaid-diagram` (algo `prose`).
- **Vert** : `migrations/044_diagram_category.sql` :
  - `ALTER … chunking_strategies_algo_check` → ajouter `'diagram'` à la liste
    autorisée (anticipe le lot 3 ; la valeur n'est pas encore utilisée).
  - `INSERT chunking_strategies` : `mermaid-diagram` algo `prose`
    (`child_target_tokens=512`, `floor=0`, `overlap=0`, `breadcrumb_depth=-1`).
    `floor=0` : on ne merge jamais un diagramme dans la prose voisine.
  - `INSERT chunking_category_strategies` : `diagram → mermaid-diagram`.
  - `INSERT chunking_extension_categories` : `.mmd`, `.mermaid` → `diagram`.

### T2.2 — Reconnaissance des fences à info-string diagramme (embarqué)
- **Rouge** : `tests/unit/indexer/test_chunking_markdown.py` — une fence
  ```` ```mermaid ```` reste atomique **quelle que soit sa taille** (déjà vrai
  via T1.4 ; ce test verrouille le comportement spécifiquement pour les
  info-strings `mermaid`/`plantuml`/`dot`).
- **Vert** : aucun code neuf attendu si T1.4 généralise bien ; sinon affiner
  `scan_fences`. (Test de non-régression / verrou.)

### T2.3 — Mapping langage (préparation lot 3)
- **Rouge** : `tests/unit/indexer/test_languages.py` (ou existant) —
  `language_for_path("d.mmd") == "mermaid"`, `.mermaid` idem.
- **Vert** : ajouter `.mmd`/`.mermaid → mermaid` dans `languages.py`
  `_LANGUAGE_BY_EXTENSION`. (Inerte tant que l'algo `diagram` n'existe pas.)

### T2.4 — Doc
- `docs/chunking.md` §3 : nouvelle ligne catégorie `diagram` ; §5 langages.

---

## LOT 3 — Projection sémantique Mermaid (design validé, à planifier en détail après 1+2)

`MermaidChunker` calqué sur `CodeChunker` : registre d'extracteurs par type +
mode générique de repli. Algo `diagram` ajouté à `_ALLOWED` (structured_factory),
`UPDATE` migration faisant passer `mermaid-diagram` de l'algo `prose` à `diagram`
(⇒ réindexation des workspaces `structured`, cf. ADR 0001 §6).

Pipeline par diagramme :
1. **Pré-normalisation** : réécriture `^\s*graph\b → flowchart` (1ʳᵉ ligne).
2. **Parse tree-sitter** (`CodeParser('mermaid')`).
3. **Extraction par type** (trio curé) → relations en **langage naturel** :
   - flowchart : `« Start mène à Choice ; si yes, Choice mène à Do thing »`
   - erDiagram : `« CUSTOMER places ORDER ; ORDER contains LINE_ITEM »`
   - sequence : `« Alice envoie à John : Hello John »`
4. **Repli générique** si `has_error` au niveau statement / type inconnu : sac de
   labels nœuds + arêtes (régex tolérant). **Jamais** de word-shred de syntaxe.
5. **Sortie small-to-big** : parent = diagramme brut ; children = projection
   passée au `TokenNormalizer` (prose → split légitime), breadcrumb préfixé.

Détail (extracteurs, schéma de la projection NL, gestion des corps d'entité
bruités) à figer dans un plan dédié une fois 1+2 livré.

---

## Vérification (chaque lot)
`uv run pytest -v` (unit + integration ciblés) · `uv run ruff check src/ tests/`
· `uv run ruff format` · pas de régression sur `test_chunking_*`.
Aucune livraison git/test sans demande explicite (CLAUDE.md).
