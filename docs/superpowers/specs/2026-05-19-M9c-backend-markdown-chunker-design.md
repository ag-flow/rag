# M9c — Markdown chunker (backend)

> **Statut** : design validé pour implémentation.
> **Spec produit ciblée** : `specs/09-roadmap.md` § « Amélioration du chunking » — chunking sémantique Markdown.
> **Prérequis** : M9 (infrastructure chunking livrée).
> **Hors-scope explicite** : code chunker (jalon distinct), frontend (M9c-front ultérieur), exposition metadata via MCP `search()`.

---

## 1. Contexte et motivation

M9 a livré l'infrastructure backend du chunking : registry de stratégies (`make_chunker`), config par workspace, champ `embeddings.metadata jsonb`, runner de migrations workspace au boot. Une seule stratégie était disponible : `paragraph` (algorithme historique, découpage par paragraphes neutres). M9c ajoute la **première stratégie sémantique** : `markdown`, qui respecte la structure d'un document Markdown (sections délimitées par headings, blocs de code préservés intacts).

Bénéfice attendu pour le RAG : un chunk « Installation » d'une doc technique reste cohérent (un titre + son contenu) au lieu d'être coupé arbitrairement à 2000 caractères. Le breadcrumb (`section_path`) capture le contexte hiérarchique pour usage futur (re-ranker plus contextuel, affichage des sources dans le client MCP).

**Frontend différé** : le `Literal["paragraph", "markdown"]` côté backend ouvre la possibilité, mais l'enum Zod du frontend M9b ne sera étendu qu'au jalon M9c-front. Conséquence : la stratégie `markdown` est configurable via API admin (`PUT /chunking-config`) mais n'apparaît pas dans le Select de l'IHM tant que M9c-front n'est pas livré.

---

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Parser **markdown-it-py** (CommonMark + GFM) | Mature, maintenu, AST stable. Standard de l'écosystème Python pour le markdown |
| D2 | Granularité **H1 + H2** par défaut, configurable via `extras.heading_levels` | Bon équilibre : assez granulaire pour le RAG, assez gros pour préserver le contexte. Configurable si besoin |
| D3 | **Fallback à `ParagraphChunker`** si aucun heading trouvé | Composition propre, réutilise l'algo testé. Aussi utilisé pour sub-split de section trop longue |
| D4 | **Metadata minimale** : `section_title`, `section_path`, `heading_level` | YAGNI. Suffisant pour breadcrumb + filtrage post-recherche. `content_type` / `language` reportés |
| D5 | **Fences préservés intacts** : pas de cut au milieu d'un bloc de code | Préserve la lisibilité pour le RAG. Trade-off : un fence > max_chars produit un chunk hors-borne |
| D6 | **Pas d'overlap autour des fences** | Couper un fence pour faire de l'overlap casse le sens du code. Cohérence sémantique > overlap systématique |
| D7 | **Breadcrumb capture tous les headings parents** (pas seulement ceux dans heading_levels) | Préserve le contexte hiérarchique. Un H3 enrichit `section_path` même s'il ne déclenche pas de split |
| D8 | `extras` Pydantic-validé, accepté `{}` (default appliqué) ou `{heading_levels: int[]}` | Cohérent avec `ChunkingConfigSpec` actuel. Pas de DB-level CHECK sur le contenu jsonb |
| D9 | **Backend seul** dans M9c (pattern M9/M9b) | Cadence claire, frontend en jalon ultérieur |
| D10 | Pas de modification du schéma `embeddings` ni de l'API MCP `search()` | Metadata stockée mais non exposée. Évolution future hors-scope |

---

## 3. Inventaire des fichiers

### 3.1 Fichiers à créer

| Fichier | Responsabilité |
|---|---|
| `backend/migrations/014_chunking_strategy_markdown.sql` | Élargit `CHECK chunking_configs.strategy IN ('paragraph','markdown')` |
| `backend/src/rag/indexer/chunking/markdown.py` | Classe `MarkdownChunker` + helper `_Section` interne |
| `backend/tests/unit/indexer/test_chunking_markdown.py` | Tests unitaires (sections, fences, fallback, breadcrumb, malformés) |
| `backend/tests/integration/test_migration_014_chunking_strategy_markdown.py` | Tests migration (accepte markdown + paragraph, rejette inconnu) |
| `backend/tests/integration/test_real_indexer_markdown.py` | Test end-to-end indexation d'un README via MarkdownChunker |

### 3.2 Fichiers à modifier

| Fichier | Modification |
|---|---|
| `backend/pyproject.toml` | Ajout dépendance `markdown-it-py>=3.0` |
| `backend/src/rag/indexer/chunking/factory.py` | Branche `if strategy == "markdown"` + helper `_make_markdown_chunker` |
| `backend/src/rag/indexer/chunking/__init__.py` | Export `MarkdownChunker` |
| `backend/src/rag/schemas/admin.py` | `Literal["paragraph"]` → `Literal["paragraph","markdown"]` + validation `extras` dispatchée par strategy |
| `backend/tests/unit/indexer/test_chunking_factory.py` | +5 tests pour la branche markdown |
| `backend/tests/unit/schemas/test_chunking_config_schema.py` | +7 tests pour markdown extras |
| `specs/09-roadmap.md` | Marquer M9c livré (à faire à la fin) |

---

## 4. Schéma `extras` et validation Pydantic

### 4.1 Shape `extras` pour `strategy="markdown"`

```ts
extras = {
  "heading_levels": [1, 2]   // liste d'entiers ∈ [1, 6], non vide, triés croissants, sans doublons
}
```

**Default** : `[1, 2]` si `extras={}`. Pas d'autre clé acceptée en V1.

### 4.2 Pattern Pydantic dans `ChunkingConfigSpec`

`schemas/admin.py` :

```python
strategy: Literal["paragraph", "markdown"]
extras: dict[str, Any] = Field(default_factory=dict)

@field_validator("extras")
@classmethod
def _validate_extras(
    cls, v: dict[str, Any], info: ValidationInfo,
) -> dict[str, Any]:
    strategy = info.data.get("strategy")
    if strategy == "paragraph":
        if v:
            raise ValueError("extras must be empty for strategy 'paragraph'")
        return v
    if strategy == "markdown":
        return _validate_markdown_extras(v)
    return v


def _validate_markdown_extras(v: dict[str, Any]) -> dict[str, Any]:
    """Accepte uniquement {heading_levels?: list[int]}. Default si absent."""
    allowed_keys = {"heading_levels"}
    extra_keys = set(v.keys()) - allowed_keys
    if extra_keys:
        raise ValueError(
            f"markdown strategy only accepts {allowed_keys}, got unknown keys: {extra_keys}"
        )
    levels = v.get("heading_levels", [1, 2])
    if not isinstance(levels, list) or not levels:
        raise ValueError("heading_levels must be a non-empty list")
    if not all(isinstance(x, int) and 1 <= x <= 6 for x in levels):
        raise ValueError("heading_levels values must be integers in [1, 6]")
    if levels != sorted(levels):
        raise ValueError("heading_levels must be sorted ascending")
    if len(set(levels)) != len(levels):
        raise ValueError("heading_levels must not contain duplicates")
    return {"heading_levels": levels}
```

Le validator actuel `_extras_empty_for_paragraph` (M9-T4) est **renommé** en `_validate_extras` et dispatch sur `strategy`. Le message d'erreur pour `paragraph` reste identique.

### 4.3 Pas de DB-level CHECK sur extras

Le contenu de `extras` reste jsonb opaque côté DB. La validation est au niveau Pydantic. La migration 014 élargit seulement `CHECK strategy IN (...)`.

---

## 5. Migration 014 et factory

### 5.1 Migration `014_chunking_strategy_markdown.sql`

```sql
-- Migration 014 — chunking_configs.strategy : ajout de 'markdown'
--
-- Symétrique à 013 (widening de CHECK constraint).
-- Permet à la stratégie 'markdown' (M9c) d'être stockée. Les extras pour
-- markdown sont validés au niveau Pydantic ({heading_levels: int[]}), pas SQL.

ALTER TABLE chunking_configs DROP CONSTRAINT chunking_configs_strategy_check;
ALTER TABLE chunking_configs ADD CONSTRAINT chunking_configs_strategy_check
    CHECK (strategy IN ('paragraph', 'markdown'));
```

**Précaution implémentation** : vérifier le nom exact de la contrainte via `\d chunking_configs` côté psql avant de DROP. Postgres génère par défaut `chunking_configs_strategy_check` (suffixe `_check`), pattern observé sur migration 012. Confirmé en M9-T1, fiable.

### 5.2 Factory `make_chunker`

```python
def make_chunker(
    *,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> ChunkerProtocol:
    if strategy == "paragraph":
        if extras:
            raise ValueError(f"paragraph strategy does not accept extras (got {extras!r})")
        return ParagraphChunker(
            max_chars=max_chars, min_chars=min_chars, overlap_chars=overlap_chars,
        )
    if strategy == "markdown":
        return _make_markdown_chunker(
            max_chars=max_chars, min_chars=min_chars,
            overlap_chars=overlap_chars, extras=extras,
        )
    raise ValueError(f"unknown chunking strategy: {strategy}")


def _make_markdown_chunker(
    *,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> MarkdownChunker:
    """Validation défensive (extras déjà validé par Pydantic au niveau API,
    mais le factory peut être appelé hors API ex: tests)."""
    allowed = {"heading_levels"}
    unknown = set(extras.keys()) - allowed
    if unknown:
        raise ValueError(f"markdown strategy unknown extras keys: {unknown}")
    heading_levels = extras.get("heading_levels", [1, 2])
    return MarkdownChunker(
        max_chars=max_chars,
        min_chars=min_chars,
        overlap_chars=overlap_chars,
        heading_levels=tuple(heading_levels),  # immutable
    )
```

`heading_levels` passé en `tuple` au constructeur pour préserver l'immutabilité.

---

## 6. Algorithme `MarkdownChunker`

### 6.1 Vue d'ensemble

```
Texte markdown
    │
    ▼
markdown-it-py → AST de tokens
    │
    ▼
Étape 1 : Découpe en SECTIONS selon heading_open ∈ heading_levels
    │
    ▼
Étape 2 : Calcule section_path (breadcrumb tous niveaux)
    │
    ▼
Étape 3 : Pour chaque section :
          - len(content) ≤ max_chars → 1 Chunk(content, metadata)
          - sinon → sub-split en préservant les fences
    │
    ▼
liste[Chunk]
```

### 6.2 Découpe en sections (`_split_into_sections`)

1. Parse `content` via `MarkdownIt("commonmark").parse(content)`.
2. Itère sur les tokens. Quand `heading_open.tag in [H{n} for n in heading_levels]` (ex: `<h1>`, `<h2>`) : marque le début d'une nouvelle section. La section précédente se termine à la ligne précédente.
3. Maintient un **stack de breadcrumb** capturant **TOUS** les headings (pas seulement ceux dans `heading_levels`) :
   - À chaque `heading_open`, pop le stack jusqu'à un niveau strictement inférieur, puis push `(level, title)`.
   - À chaque section déclenchée, `section_path = [title for level, title in stack[:-1]]` (sans le titre courant qui est dans `section_title`).
4. Reconstruit le texte source de chaque section via les indices de lignes du document original (champ `token.map` de markdown-it-py, `[start_line, end_line]` exclusif sur la fin).
5. **Cas particulier — aucun heading aux niveaux configurés** : aucune section produite → délègue le contenu entier à `ParagraphChunker` interne. Les chunks retournés sont **enrichis** avec `{section_title: None, section_path: [], heading_level: 0}` pour préserver l'invariant §7.1 (toutes les 3 clés toujours présentes).
6. **Cas particulier — préambule** : texte avant le 1er heading → section "fictive" avec `section_title=None`, `section_path=[]`, `heading_level=0`. Même shape de metadata que le cas no-heading — c'est la valeur "neutre" du contrat.

### 6.3 Sub-split d'une section longue (`_split_section`)

Quand `len(section_content) > max_chars` :

1. **Identifier les zones fence** dans la section via les tokens `fence` retournés par markdown-it-py (positions de ligne `token.map`).
2. **Découper en blocs alternés** `(text_block, fence_block, text_block, ...)`.
3. **Pour chaque text_block** :
   - Si `len ≤ max_chars` → 1 chunk.
   - Sinon → délègue à `ParagraphChunker` interne (mêmes `max_chars`/`min_chars`/`overlap_chars`).
4. **Pour chaque fence_block** :
   - Si `len ≤ max_chars` → chunk unique intact.
   - Si `len > max_chars` → chunk unique hors-borne (trade-off documenté).
5. **Re-assemble** : enrichit chaque chunk produit avec les `metadata` de la section parente.

**Note overlap** : l'overlap pattern de `ParagraphChunker` est conservé **entre text_blocks** d'une même section, mais **PAS** autour des fences (le fence reste un chunk autonome sans overlap avant/après).

### 6.4 Composition avec `ParagraphChunker`

```python
class MarkdownChunker:
    def __init__(self, *, max_chars, min_chars, overlap_chars, heading_levels):
        self._max_chars = max_chars
        self._min_chars = min_chars
        self._overlap_chars = overlap_chars
        self._heading_levels = heading_levels  # tuple[int, ...]
        self._paragraph_fallback = ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )

    def chunk(self, content: str) -> list[Chunk]:
        sections = self._split_into_sections(content)
        if not sections:
            return self._enrich_with_neutral_metadata(
                self._paragraph_fallback.chunk(content),
            )
        result: list[Chunk] = []
        for section in sections:
            result.extend(self._chunk_section(section))
        return result

    @staticmethod
    def _enrich_with_neutral_metadata(chunks: list[Chunk]) -> list[Chunk]:
        """Pour le cas no-heading : ré-emballe chaque Chunk avec la valeur
        neutre de metadata (section_title=None, section_path=[], heading_level=0).
        Nécessaire car Chunk est frozen — on ne peut pas muter chunk.metadata."""
        neutral = {"section_title": None, "section_path": [], "heading_level": 0}
        return [Chunk(content=c.content, metadata=neutral) for c in chunks]
```

`Chunk` est `frozen=True` (M9-T3) : on ne peut pas muter `chunk.metadata` après création. Tout enrichissement de metadata passe par la création d'un **nouveau** `Chunk(content=..., metadata=...)`. Le `MarkdownChunker` applique ce pattern dans deux contextes :
- Le fallback no-heading (méthode `_enrich_with_neutral_metadata` ci-dessus).
- Le sub-split d'une section longue : chaque chunk produit par `ParagraphChunker` interne est ré-emballé avec le metadata de la section parente avant d'être ajouté au résultat (cf. §6.3 step 5).

### 6.5 Type interne `_Section`

```python
@dataclass
class _Section:
    title: str | None      # None pour le préambule
    path: list[str]        # breadcrumb des parents (tous niveaux confondus)
    level: int             # 0 pour préambule, 1-6 pour les autres
    content: str           # texte source brut de la section, fences inclus
```

Privé au module `markdown.py`, jamais exposé. `MarkdownChunker.chunk()` retourne uniquement des `Chunk`.

---

## 7. Contrat metadata `Chunk.metadata`

### 7.1 Shape exact

Pour chaque `Chunk` produit par `MarkdownChunker.chunk()` :

```python
{
    "section_title": str | None,    # None si préambule
    "section_path": list[str],      # breadcrumb des parents ; vide si préambule
    "heading_level": int,           # 0 si préambule, sinon 1..6
}
```

**Invariants** :
- Ces 3 clés sont toujours présentes, jamais plus, jamais moins.
- `section_path` n'inclut **pas** le titre de la section courante.
- Si plusieurs chunks proviennent du sub-split d'une même section longue, ils partagent **les mêmes** metadata.

### 7.2 Exemple concret

Document :
```markdown
Introduction libre.

# Getting Started

Préambule de la section.

## Installation

Texte d'install...

### From source

Détails build...

## Usage

Comment utiliser.

# Reference

API complète.
```

Avec `heading_levels=[1, 2]`, le chunker produit (au moins) :

| # | section_title | section_path | heading_level | content (extrait) |
|---|---|---|---|---|
| 1 | `None` | `[]` | `0` | "Introduction libre." |
| 2 | `"Getting Started"` | `[]` | `1` | "# Getting Started\n\nPréambule…" |
| 3 | `"Installation"` | `["Getting Started"]` | `2` | "## Installation\n\nTexte…\n\n### From source\n\nDétails…" |
| 4 | `"Usage"` | `["Getting Started"]` | `2` | "## Usage\n\nComment utiliser." |
| 5 | `"Reference"` | `[]` | `1` | "# Reference\n\nAPI complète." |

Le H3 « From source » enrichirait `section_path` s'il déclenchait un split, mais avec `heading_levels=[1, 2]` il reste absorbé dans la section H2 parente.

### 7.3 Persistance

`workspace_embeddings.upsert_chunks` (livré M9-T6) compatible nativement : `json.dumps(dict(chunk.metadata))` à l'INSERT. La colonne `embeddings.metadata jsonb` accueille la structure sans modification de schéma.

---

## 8. Hors-scope MCP `search()`

Le contrat actuel de `mcp.py:search()` retourne `content` uniquement, pas `metadata`. M9c **ne modifie pas** ce contrat. La metadata est stockée en base mais non exposée. Une évolution future (M10+) pourra l'inclure dans la réponse MCP pour améliorer la pertinence côté agent client (afficher le breadcrumb du chunk dans les sources).

---

## 9. Tests

### 9.1 `tests/unit/indexer/test_chunking_markdown.py`

**Cas de base (4 tests)** : empty, no-heading fallback, single H1, H1+H2 split avec metadata.

**Breadcrumb (3 tests)** : capture parents in-levels, capture parents out-of-levels (absorbés), préambule.

**Sub-split (3 tests)** : section longue partage metadata, fence préservé intact, fence géant > max_chars.

**Configuration heading_levels (3 tests)** : `[1]` groupe les sous-sections, `[1,2,3]` split à chaque H3, `[3]` seul (H1 devient préambule, H3 splits).

**Contrats metadata (2 tests)** : clés exactes, JSON-serializable.

**Robustesse Markdown malformé (2 tests)** : fence non clôturé (parser le traite comme texte), setext heading (`Title\n=====`).

Total : **17 tests unitaires**.

### 9.2 Extension `test_chunking_factory.py` (5 tests)

- `test_make_chunker_markdown_returns_markdown_chunker`
- `test_make_chunker_markdown_default_heading_levels` (extras={} → (1,2))
- `test_make_chunker_markdown_custom_heading_levels`
- `test_make_chunker_markdown_rejects_unknown_extras_key`
- `test_make_chunker_markdown_immutable_levels` (tuple, pas list)

### 9.3 Extension `test_chunking_config_schema.py` (7 tests)

- happy path default extras (normalisé en `{heading_levels:[1,2]}`)
- custom heading_levels valide
- rejette unknown extras key
- rejette empty heading_levels
- rejette out-of-range levels (`[0]`, `[7]`)
- rejette unsorted levels (`[2,1]`)
- rejette duplicate levels (`[1,1]`)

### 9.4 `test_migration_014_chunking_strategy_markdown.py` (3 tests)

- accepte `strategy='markdown'`
- accepte toujours `strategy='paragraph'` (non-régression)
- rejette une stratégie inconnue (`'foo'`)

### 9.5 `test_real_indexer_markdown.py` (1 test e2e)

- Crée workspace via `create_workspace`.
- UPDATE `chunking_configs SET strategy='markdown', extras='{"heading_levels":[1,2]}'`.
- Recrée table `embeddings` à dim=8 (pattern M9-T6).
- `RealIndexer.index_file(content=README_DEMO_MD)` :
  - Plusieurs chunks créés.
  - `embeddings.metadata` contient `section_title`, `section_path`, `heading_level`.
  - Au moins un chunk a `heading_level=1`.

### 9.6 Non-régression

Toutes les suites existantes (`tests/unit/indexer/`, `tests/integration/`, `tests/api/`) restent vertes.

### 9.7 Pas de tests frontend

Frontend reporté à un jalon ultérieur. Le `Literal["paragraph","markdown"]` côté backend est élargi, le frontend M9b continue à n'exposer que `"paragraph"`. La stratégie `markdown` est configurable uniquement via API admin tant que le frontend n'est pas mis à jour.

---

## 10. Plan de livraison et numérotation

- **M9c** = ce jalon (backend markdown chunker).
- **M9c-front** (ultérieur, séparé) = étendre le frontend pour exposer `markdown` dans le Select stratégie + i18n FR/EN + champ `extras.heading_levels` éventuel.
- **M9d** (ultérieur) = code chunker (langage-aware via tree-sitter ou heuristique simple).

Découpage des tâches au plan d'implémentation (rédigé après validation de la spec) :

1. Ajout dépendance `markdown-it-py` + migration 014 + tests migration
2. Élargissement DTO `ChunkingConfigSpec` (Literal + validation extras dispatchée) + tests
3. Classe `MarkdownChunker` (algorithme + composition ParagraphChunker) + tests unitaires
4. Extension `factory.make_chunker` + tests factory
5. Export module + intégration end-to-end (`test_real_indexer_markdown`)
6. Roadmap + smoke final

---

## 11. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| API `markdown-it-py` change entre versions | Pin `markdown-it-py>=3.0,<4.0` dans `pyproject.toml`. Tests d'intégration vérifient la reconstruction de texte depuis `token.map` |
| `token.map` retourne `None` pour certains tokens (HTML inline, références) | Le découpage en sections se base sur les tokens `heading_open` et `fence` qui ont toujours `token.map` renseigné. Vérifié dans l'algo |
| Fence géant > max_chars produit un chunk hors-borne | Décision D5 documentée. Edge case rare en pratique (un bloc de code de 2000+ chars est exceptionnel) |
| Markdown malformé (fence non clôturé, etc.) | markdown-it-py est tolérant, traite gracieusement les cas tordus. Tests dédiés (§9.1 robustesse) |
| Migration 014 sur DB existante avec workspaces déjà configurés en `paragraph` | CHECK widening conserve la stratégie existante (`'paragraph'` toujours accepté). Pattern hérité de 013, sans risque |
| Frontend ne propose pas `markdown` mais backend l'accepte → un admin curieux pourrait configurer markdown via API et "casser" l'IHM | L'IHM affichera le Select en mode "valeur inconnue". Mineur, le admin a fait un choix conscient. Sera résolu à M9c-front |

---

## 12. Hors-scope explicite

- **Frontend** : reporté à M9c-front (ou regroupé avec un futur code chunker M9d).
- **Code chunker** (`strategy="code"`) : jalon distinct (M9d ou +). Architecture similaire mais avec parsing langage-aware.
- **Exposition `metadata` via MCP `search()`** : non couvert. La metadata est stockée mais pas retournée au client agent.
- **Content_type / language** dans metadata : reporté. Premier besoin est le breadcrumb.
- **Configuration de `split_code_blocks`** : décision D5 implicitement câblée (fence toujours préservé). Pas exposé en `extras`.
