# ADR 0001 — Chunking structure-aware par type de fichier

- **Statut** : **accepté** (2026-06-22) — §6 tranché : estimateur tokens heuristique pluggable ; `code-aware` en tree-sitter, livré en **Lot 2** après le Lot 1.
- **Date** : 2026-06-22
- **Contexte d'audit** : voir Phase 1 (résumé §1). Sources `backend/src/rag/…`.
- **Branche cible** : `dev`. Implémentation Phase 3 **derrière flag**, ancien et nouveau pipeline coexistent.

---

## 1. Résumé de l'état actuel (rappel d'audit)

| Sujet | État | Source |
|---|---|---|
| Découpe | char-based (`max_chars`), 2 stratégies `paragraph` / `markdown` | `indexer/chunking/{paragraph,markdown}.py` |
| Unité dédup | **fichier** : `sha256(content)` dans `indexed_documents` | `sync/executor.py:211,519` |
| Upsert chunks | `replace` = `DELETE WHERE path` + INSERT **tous** | `db/workspace_embeddings.py:43-50` |
| Breadcrumb | `section_path` **stocké en metadata, jamais embeddé** | `markdown.py:154`, `real.py:133` |
| Limite tokens | **inexistante** comme config consommée (que de la prose) | `model_dimensions` (005/037), `pricing.yml` |
| Dépassement | non géré : erreur opaque `HTTP 400` ; fence de code émise **non bornée** | `adapter.py:117`, `markdown.py:181-183` |
| Réindex | binaire par fichier → re-embed **total** du fichier | `executor.py:219,527` |

Trois faiblesses structurantes : (a) aucune source de vérité des limites de tokens ; (b) le breadcrumb est capturé mais inerte ; (c) dédup tout-ou-rien par fichier, aucune réutilisation de chunk.

---

## 2. Modèle cible — routage par type (décisions verrouillées)

Résolution de la stratégie, par ordre de priorité décroissante :

1. **Override explicite à l'appel** (ad hoc API) — `PushRequest` porte un `strategy: str | None` optionnel qui référence une **stratégie nommée** du catalogue. Prime sur tout.
2. **Résolution par type** (toujours possible, `path` présent en sync **et** en ad hoc) :
   `extension → catégorie → stratégie nommée`.
3. **Défaut** — catégorie `prose` → stratégie par défaut du workspace.

Trois objets de configuration, chacun avec **défaut global seedé + surcharge par workspace** :

```
catalogue de stratégies nommées        ext → catégorie            catégorie → stratégie
─────────────────────────────          ──────────────            ─────────────────────
markdown-deep {algo:markdown, …}        .md .txt  -> prose         prose -> markdown-deep
code-aware    {algo:code, …}            .py .ts .sql .go -> code   code  -> code-aware
table         {algo:table, …}           .csv .tsv -> table         table -> table
prose-basic   {algo:paragraph, …}       .json .yaml -> data        data  -> code-aware*
```

\* `data` cartographié provisoirement vers `code-aware` (structuré), cf. §4.4.

**Résolution effective** = merge `global` puis `workspace` (le workspace surcharge clé par clé). Catégorie inconnue / extension non mappée → `prose`.

---

## 3. Les 5 axes — décisions et trade-offs

### Axe 1 — Injection du breadcrumb de titres

**Décision** : préfixer le **texte embeddé** (pas le texte stocké brut) par le chemin hiérarchique des titres, paramétrable par stratégie via `breadcrumb_depth` :

- `0` : désactivé.
- `N>0` : N derniers niveaux.
- `-1` : chemin complet (défaut pour `markdown-deep`).

Format : `"# A > ## B > ### C\n\n<contenu>"`. Le breadcrumb compte **dans le budget de tokens** (cf. axe 3) et **dans le hash** (cf. axe 5).

**Trade-off** : chemin complet = désambiguïsation maximale (deux sections « Limitations » dans deux chapitres distincts deviennent distinguables) au prix de quelques tokens par chunk ; N-derniers = contexte local moins cher mais perd l'ancrage racine. **Justification du défaut `-1`** : le corpus est technique (specs/docs profondes, code), la dilution est négligeable au regard du gain de rappel, et la donnée `section_path` est **déjà calculée** (`markdown.py:125`) — coût d'implémentation marginal. On expose `breadcrumb_depth` pour les corpus à hiérarchie très profonde où l'on voudra plafonner.

### Axe 2 — Small-to-big (parent-child)

**Décision** : embed l'enfant (unité fine + breadcrumb), **retourne le parent** (section/symbole/table entière) au LLM. Modèle de données : **table `sections` parente + FK depuis `embeddings`**, dans la base `rag_<ws>`.

```sql
-- nouvelle table parente
CREATE TABLE sections (
    id          BIGSERIAL PRIMARY KEY,
    path        TEXT NOT NULL,
    section_key TEXT NOT NULL,          -- identité stable de la section (cf. axe 5)
    content     TEXT NOT NULL,          -- texte PARENT renvoyé au LLM
    metadata    JSONB NOT NULL DEFAULT '{}',
    UNIQUE (path, section_key)
);
-- embeddings = enfants, pointent vers leur parent
ALTER TABLE embeddings ADD COLUMN section_id BIGINT REFERENCES sections(id) ON DELETE CASCADE;
```

Granularité parent/enfant **portée par la stratégie** :

| stratégie | enfant embeddé | parent renvoyé |
|---|---|---|
| `markdown-deep` (prose) | paragraphe + breadcrumb | section H{n} entière |
| `code-aware` (code) | symbole / fenêtre de lignes + breadcrumb de portée | fonction/classe (ou fichier si atomique) |
| `table` | en-tête + groupe de N lignes | table entière |

**Récupération** (`db/workspace_search.py:35`) : vector search sur les enfants → **dédup par `section_id`** → fetch `sections.content` → renvoi. Plusieurs enfants d'une même section ⇒ section renvoyée **une seule fois** (avec le meilleur score).

**Trade-off** : duplication de stockage (le texte enfant est inclus dans le parent) contre précision de récupération (on cible le paragraphe) + complétude de génération (on donne la section). **Justification** : sur du code/spec, renvoyer un paragraphe orphelin casse le sens ; le surcoût stockage est acceptable (texte, pas vecteur). On peut, en option future, ne stocker `sections.content` que par delta — hors scope MVP.

### Axe 3 — Normalisation des bornes (floor / ceiling) **en tokens**

**Prérequis bloquant** (cf. audit) : créer la **source de vérité des limites**. Décision :

```sql
ALTER TABLE model_dimensions
    ADD COLUMN max_input_tokens INT NOT NULL DEFAULT 8192,   -- limite dure provider
    ADD COLUMN token_char_ratio NUMERIC NOT NULL DEFAULT 4.0; -- estimateur chars→tokens
```

Seed depuis la prose du `pricing.yml` / docs modèles (openai 8191, voyage-* 32000, jina/nomic 8192, dashscope 8192, gemini 2048/8192…). **Cette colonne devient l'unique source de vérité** (invariant 3).

**Deux plafonds distincts** :
- **`provider_hard_ceiling`** = `floor(0.8 × max_input_tokens)` — limite **infranchissable** (marge de sécurité 20 % pour l'imprécision de l'estimateur). Tout dépassement après split = erreur typée explicite (cf. invariant 2), **jamais** d'envoi silencieux.
- **`child_target_tokens`** (param stratégie, ex. 384) — taille **cible de récupération** de l'enfant, très inférieure au plafond provider. C'est le vrai levier qualité.

Algorithme de normalisation :
- **Floor** : merge des blocs `< floor_tokens` (param, ex. 64) vers le haut tant que la somme `< child_target_tokens`. Remplace le coalesce char-based (`paragraph.py:51`).
- **Ceiling** : split des blocs `> child_target_tokens` sur frontière naturelle, avec overlap **en tokens**. Remplace le split char-based (`paragraph.py:81`).
- **Garde-fou dur** : tout chunk (enfant **ou** parent) dépassant `provider_hard_ceiling` est re-splité ; si une unité atomique indivisible dépasse encore → `EmbeddingChunkTooLarge` (nouvelle sous-classe de `EmbeddingProviderError`) + log explicite. Corrige le bug de la fence non bornée (`markdown.py:181-183`).

**Estimation de tokens** — décision : **estimateur heuristique** `ceil(len(text) / token_char_ratio)`, ratio par modèle, marge 20 %. **Trade-off** : tokenizer exact (tiktoken/HF) = précis mais dépendance lourde + un tokenizer par provider ; heuristique = zéro dépendance, portable, légèrement conservateur. **Justification** : la marge couvre l'imprécision ; l'interface `TokenEstimator` reste pluggable pour brancher un tokenizer exact plus tard sans toucher au pipeline. → **point à valider** (§6).

### Axe 4 — Routage par type (comportement par catégorie)

- **prose** (`markdown-deep`) : sections par titres + breadcrumb (algo markdown actuel, durci tokens). Préambule = section `level 0`. Fallback paragraphe si aucun titre.
- **code** (`code-aware`) : découpe **par symboles** (fonction/classe/bloc top-level), jamais au milieu d'une chaîne/expression ; breadcrumb = portée (`module > classe > méthode`) ; parent = symbole englobant. **Remplace** le traitement actuel (fence émise entière non bornée). **Trade-off** : tree-sitter (multi-langage, robuste, mais dépendance + grammaires) vs heuristique par regex/indentation (légère, fragile sur langages exotiques). → **point à valider** (§6).
- **table** (`table`) : conserve la ligne d'en-tête, découpe par **groupes de lignes** (param `rows_per_chunk`), chaque enfant = en-tête + N lignes ; parent = table entière. **Jamais** de char-split (corrige le déchiquetage actuel des tables passées en prose).
- **data** (json/yaml) : provisoirement routé vers `code-aware` (texte structuré). Un algo `structured` dédié (découpe par clés top-level) est listé en évolution, **hors scope MVP** — signalé pour ne pas sous-traiter à moitié.

### Axe 5 — Stabilité à la réindexation (hash niveau bloc normalisé)

**Décision** : passer du hash **fichier** au hash **par chunk normalisé**, et de l'upsert `replace` (DELETE all + INSERT all) à un **diff ensembliste**.

```sql
ALTER TABLE embeddings ADD COLUMN chunk_hash TEXT NOT NULL;
-- identité d'un chunk = (path, chunk_hash), PLUS (path, chunk_index)
ALTER TABLE embeddings DROP CONSTRAINT embeddings_path_chunk_index_key;
ALTER TABLE embeddings ADD CONSTRAINT embeddings_path_hash_key UNIQUE (path, chunk_hash);
CREATE INDEX ON embeddings (path);
```

- `chunk_hash = sha256(texte EXACT embeddé)` — **breadcrumb inclus** : si un titre parent est renommé, le texte embeddé change → re-embed légitime. Le hash doit refléter **ce qui a été embeddé**, sinon incohérence.
- `chunk_index` devient un simple **ordre de présentation**, plus une identité.
- **Réindex incrémentale** : calcul du nouvel ensemble `{chunk_hash}` → `DELETE` les hashes disparus, `INSERT` les nouveaux, **conserve les inchangés (pas de re-embed)**. Le hash fichier (`indexed_documents`) reste comme court-circuit de premier niveau (skip total si le fichier entier est identique).

**Trade-off** : diff ensembliste = upsert plus complexe contre invariant tenu (seuls les chunks réellement modifiés sont ré-embeddés) + coût d'embedding réduit. **Justification** : c'est la condition pour que « une édition locale n'invalide que les chunks modifiés » soit vrai ; aujourd'hui c'est faux par construction. Sensibilité aux glissements de frontières : le hash portant sur le **contenu normalisé** (et non l'offset), une insertion en début de fichier ne décale plus les hashes des blocs suivants → ils sont reconnus inchangés.

---

## 4. Changements de schéma — récapitulatif

**Base config (`backend/migrations/`)** — nouvelles migrations numérotées :
- `chunking_strategies` : catalogue nommé `(scope, workspace_id?, name, algo, params jsonb)`.
- `chunking_extension_categories` : `(scope, workspace_id?, extension, category)`.
- `chunking_category_strategies` : `(scope, workspace_id?, category, strategy_name)`.
- `model_dimensions` : `+ max_input_tokens`, `+ token_char_ratio` (source de vérité limites).
- `chunking_configs` (actuel, 1 row/ws) : **déprécié** dans son rôle de stratégie unique ; migration de ses valeurs vers une stratégie nommée seedée + assignation `prose`. Conservé transitoirement pour le pipeline `legacy` derrière flag.
- `PushRequest` / endpoint `POST /workspaces/{name}/index` : `+ strategy: str | None`.

**Base workspace (`backend/src/rag/db/workspace_migrations/versions/`)** :
- `sections` (parent) + `embeddings.section_id` FK.
- `embeddings.chunk_hash` + bascule contrainte unique `(path, chunk_index)` → `(path, chunk_hash)`.

---

## 5. Stratégie de migration & bascule

1. **Flag** `chunking.engine = legacy | structured` (config workspace). Par défaut `legacy` → aucun changement de comportement tant qu'on ne bascule pas.
2. Les nouvelles colonnes/tables sont créées à vide ; le pipeline `legacy` les ignore.
3. **Bascule = réindex complète du workspace** : l'injection du breadcrumb change le texte embeddé → les vecteurs `legacy` sont incomparables aux nouveaux. Donc à l'activation `structured`, un job `reindex_chunking_change` (réutilise l'infra migrations 013) re-traite **tout le corpus du workspace une fois**.
4. **Après** la bascule, les éditions suivantes sont **incrémentales** (diff par `chunk_hash`, axe 5).
5. Bascule **par workspace**, jamais globale → pas d'indisponibilité de l'ensemble.

---

## 6. Décisions d'architecte (tranchées le 2026-06-22)

1. **Estimation de tokens (axe 3)** — ✅ **heuristique pluggable** (`len/ratio` + marge 20 %) via une interface `TokenEstimator` ; tokenizer exact branchable plus tard sans toucher au pipeline.
2. **`code-aware` (axe 4)** — ✅ **tree-sitter**, traité comme **chantier à part (Lot 2)**.

### Découpage en lots

- **Lot 1 (ce chantier)** : infra routage (catalogue + catégories + assignations, résolution global→workspace→override) ; source de vérité tokens ; `TokenEstimator` ; normaliseur en tokens (floor/ceiling/overlap + garde-fou dur) ; breadcrumb injecté ; stratégies `prose` (markdown durci) et `table` ; small-to-big (`sections` + `section_id`) ; hash par chunk + diff ensembliste ; flag `legacy|structured` ; tests + harnais de diff de chunks. La catégorie `code` est **temporairement routée vers `prose`** en Lot 1 (pas de char-split sauvage : le garde-fou tokens s'applique).
- **Lot 2** : stratégie `code-aware` tree-sitter (grammaires, build, breadcrumb de portée, parent = symbole) + catégorie `data` structurée.

---

## 7. Definition of done (rappel)

Audit ✅ → **ADR validé (ce document)** → impl derrière flag → tests verts (breadcrumb, merge/split bornes, routage code/table, idempotence hash) → diff de chunks ancien/nouveau pour inspection humaine avant bascule.
