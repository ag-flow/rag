# Design — détection de la branche par défaut du remote

**Date** : 2026-05-28
**Statut** : validé (design), en attente revue spec écrit

## Contexte

Le support d'une branche git spécifique existe déjà de bout en bout :

| Étape | Où | Comportement actuel |
|---|---|---|
| Saisie | `frontend/.../AddSourceDialog.tsx` | Champ « branch », pré-rempli `main`, obligatoire (`z.string().min(1).default("main")`) |
| Transport | `SourceCreateRequest.config` | La branche voyage dans `config.branch` |
| Lecture | `backend/.../sync/executor.py:240` | `branch = config.get("branch", "main")` |
| Clone | `backend/.../sync/git_ops.py:102` | `git clone --branch <branch>` |
| Pull | `backend/.../sync/git_ops.py:132,138` | `git fetch origin <branch>` + `git reset --hard origin/<branch>` |
| Erreur branche absente | `git_ops.py:81-83` | `GitCloneError` (stderr sanitizé) stockée dans `index_jobs.error_message` |

**Problème** : le défaut `main` est codé en dur (frontend **et** backend). Sur un dépôt dont
la branche par défaut est `master` / `develop` / autre, si l'utilisateur laisse le champ
inchangé, le clone échoue. La branche est modifiable manuellement, donc rien n'est cassé —
mais c'est un piège silencieux.

**Objectif** : quand l'utilisateur ne précise pas de branche, détecter la branche par défaut
réelle du dépôt distant au lieu de forcer `main`.

## Décisions validées

1. **Moment de résolution** : à l'écriture (création / édition de la source). On résout une
   fois et on stocke la branche concrète en DB. Déterministe, visible, modifiable. Si le dépôt
   change sa branche par défaut plus tard, la source garde celle résolue.
2. **Sémantique UX** : champ branche **optionnel**. Vide = détection automatique à
   l'enregistrement. Rempli = branche explicite, aucune détection.
3. **Échec de détection** : repli sur `main` **avec avertissement** — log `warning` structuré
   + message non bloquant remonté à l'IHM. La source est créée malgré tout (pas de blocage).
   Le cas nominal (détection réussie) stocke la vraie branche ; seul le cas dégradé porte
   l'avertissement. Ce choix conserve l'absence de friction à la création tout en évitant un
   échec totalement masqué (conforme à « pas de fallback muet »).

## Architecture

### 1. Détection — `backend/src/rag/sync/git_ops.py`

Nouvelle fonction pure, sans effet de bord, qui **ne lève pas** (le repli est de la
responsabilité de l'appelant) :

```python
async def detect_default_branch(
    *, url: str, token: str | None, timeout: float = 15.0
) -> str | None:
    """Branche par défaut du remote via `git ls-remote --symref <url> HEAD`.

    Retourne le nom de branche (ex: "main", "master", "develop"), ou None si
    indéterminable (échec réseau, timeout, repo injoignable, pas de symref HEAD).
    """
```

- Commande : `git ls-remote --symref <auth_url> HEAD`.
- Sortie attendue :
  ```
  ref: refs/heads/main	HEAD
  <sha>	HEAD
  ```
  Parser la ligne `ref: refs/heads/<branch>\tHEAD` → extraire `<branch>`.
- Réutilise les helpers existants : `_build_authenticated_url(url, token)`,
  `GIT_TERMINAL_PROMPT=0`, `sanitize_git_output`.
- Timeout via `asyncio.wait_for` (15 s, comme `test_source_connection`).
- Tout échec (returncode != 0, timeout, absence de ligne symref) → `None`.

### 2. Résolution — `backend/src/rag/services/sources.py`

Helper interne :

```python
async def _resolve_branch_for_write(
    config: dict, *, token: str | None
) -> tuple[dict, str | None]:
    """Renvoie (config avec branche concrète, message d'avertissement | None)."""
```

Logique :
- `config.get("branch")` non vide → renvoyer `(config, None)` (branche explicite, pas de détection).
- Sinon → `detected = await detect_default_branch(url=config["url"], token=token)` :
  - `detected` non None → `config["branch"] = detected`, warning `None`.
  - `detected` None → `config["branch"] = "main"`, `log.warning("source.branch_detect_failed", ...)`,
    warning = message i18n-able (ex: clé courte côté backend, texte affiché côté frontend).

Intégration :
- **`add_source`** : token = `request.auth_value` (PAT en clair fourni, ou `None` pour repo public).
  Appel du helper **avant** l'`INSERT`. La config persistée contient la branche résolue.
- **`update_source`** : token = `request.auth_value` si refourni, sinon résolution de l'`auth_ref`
  existant via `resolver.resolve_with_retry`. Nouveau paramètre `resolver` (même type
  `_ResolverProtocol` que `test_source_connection`). Appel du helper **avant** l'`UPDATE`.
- Les deux services retournent un dict enrichi de `branch_warning: str | None`.

### 3. Schéma & API

- `backend/src/rag/schemas/admin.py` — `SourceResponse` : ajout `branch_warning: str | None = None`.
- `SourceCreateRequest` / `SourceUpdateRequest` : **inchangés**. La branche transite déjà dans
  `config` (dict libre) ; quand elle est absente, la détection s'applique.
- `backend/src/rag/api/admin.py` — `post_source` et `patch_source` passent
  `resolver=request.app.state.resolver` (déjà disponible, utilisé par `test_source_connection`).

### 4. Frontend — `frontend/src/pages/workspace/AddSourceDialog.tsx`

- `createSchema` / `editSchema` : `branch: z.string().optional()` (retrait de `.min(1).default("main")`).
- `defaultValues.branch` = `""` (au lieu de `"main"`). En édition, recharge `source.config.branch`
  tel quel (peut être vide si jamais résolu — cas théorique, sources existantes ont déjà une branche).
- `BranchField` : placeholder « branche par défaut du dépôt (ex: main) », label marqué optionnel.
- Soumission (`onSubmitCreate` / `_saveEdit`) : `branch` **omis** de `config` si vide après `trim()`
  (ne pas envoyer `branch: ""`).
- Réponse de mutation : si `branch_warning` présent → `toast({ variant: "warning"/"default", title })`.
- i18n fr/en : nouvelles clés `sources.fields.branch_placeholder`, `sources.fields.branch_optional_hint`,
  `sources.add.branch_warning` (et équivalent edit).

## Gestion d'erreur

| Cas | Comportement |
|---|---|
| Branche fournie explicitement | Aucune détection, stockée telle quelle |
| Branche vide, détection OK | Branche réelle stockée, pas d'avertissement |
| Branche vide, remote injoignable / token absent / timeout / pas de symref | Repli `main` + `log.warning` + `branch_warning` non bloquant remonté à l'IHM (toast) |
| Échec d'écriture DB après détection | Inchangé : rollback du secret Harpocrate déjà géré dans `add_source` |

## Tests (TDD)

**Unit backend**
- `detect_default_branch` : parsing symref présent (`main`, `master`), absence de ligne symref,
  sortie vide, mock du subprocess pour returncode != 0 → `None`.
- `_resolve_branch_for_write` : branche explicite préservée ; détection OK → branche détectée ;
  détection échouée → `main` + warning non nul.

**Integration backend** (fixture git locale `tests/integration/_git_fixture.py`)
- `add_source` branche vide sur un repo dont le défaut est `master` → config stockée avec `master`.
- `update_source` branche vidée → re-résolution.
- repo injoignable → `main` + `branch_warning` peuplé.

**Frontend** (Vitest + RTL)
- Champ branche vide → payload `config` **sans** clé `branch`.
- Branche saisie → `config.branch` présent.
- Réponse avec `branch_warning` → toast d'avertissement affiché.

## Hors scope

- Enrichir `test_source_connection` pour afficher la branche détectée (amélioration future, YAGNI).
- Correction des tests obsolètes `test_source_create_git_minimal` (unit) et
  `test_services_sources.py:94,122` (integration), cassés par le commit `4492f76` qui a rendu
  `name`/`api_key_vault` obligatoires. Orthogonal à cette feature — à traiter séparément.
