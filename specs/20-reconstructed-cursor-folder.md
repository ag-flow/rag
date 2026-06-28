# 20 — Curseur reconstruit + adaptateur `folder`

> **Disclaimer.** S'appuie sur l'interface `Source` de `19` (contrat + garanties). Avant d'implémenter, **revérifie** : l'emplacement final de `ChangeSet` (neutralisé hors `git_ops` en `19`), la requête `indexed_documents` pour déduire les suppressions, le format de `cursor` JSONB. **Context7**, **Serena**, skill **`brainstorming`**. `19` **doit être livré** d'abord (cette spec n'a de sens que branchée sur l'interface).

## Position dans la série

Deuxième des trois chantiers. Dépend de `19`. Livre **la primitive réutilisable** (le travail dur) + **`folder`** comme première source du profil *curseur reconstruit* — la plus simple, pour prouver le mécanisme **sans** auth ni normalisation. `21` (source REST) n'ajoutera ensuite que les complications réelles par-dessus une primitive déjà éprouvée.

## Rôle

Fournir le **profil « curseur reconstruit »** du contrat `Source` : *le rag fabrique le delta pour les sources qui ne savent pas le faire elles-mêmes* (folder, source REST, S3). C'est le **principe unificateur** acté : git/docflow ont un journal natif ; tout le reste, le rag le reconstruit par balayage `lastModified`.

**Pourquoi `folder` d'abord** : il isole le **mécanisme pur** (énumérer, comparer, déduire le delta) de tout le bruit réel (auth, permissions, storage-format). Une fois la primitive prouvée sur le cas le plus simple, une source distante devient un adaptateur, pas un chantier.

## La primitive `ReconstructedCursorSource`

Classe de base qui **implémente `changes_since`** ; un adaptateur n'a plus qu'à fournir deux choses :

```python
class ReconstructedCursorSource(Source):
    async def enumerate(self) -> list[ItemRef]: ...        # adapter : TOUS les items + last_modified
    async def fetch_content(self, unit) -> str | None: ... # adapter : contenu d'un item

    # FOURNI par la primitive :
    async def changes_since(self, cursor) -> ChangeDelta:
        items = await self.enumerate()                         # complet ou lève (garantie 19)
        prev  = await load_indexed_paths(workspace, source_id) # SCOPÉ PAR SOURCE (cf. point critique)
        since = cursor.last_modified if cursor else None       # None au 1er run → tout est candidat
        added_modified = [i for i in items
                          if since is None or i.last_modified > since or i.id not in prev]
        deleted        = [p for p in prev if p not in {i.id for i in items}]
        newest         = max(i.last_modified for i in items)
        new_cursor     = newest - OVERLAP                      # fenêtre de recouvrement (clock skew)
        return ChangeDelta(ChangeSet(added/modified split via prev, deleted),
                           {"last_modified": new_cursor})
```

### Les deux idées qui rendent ça robuste (avec leurs limites réelles)

1. **`lastModified` = signal, `content_hash` = vérité — mais seulement contre les faux *positifs*.** Le `lastModified` décide *quoi regarder* ; la réalité du changement est tranchée par le **dedup `content_hash`** du moteur (`19`). Un faux **positif** (un `touch` sans modif) est re-fetché, re-hashé, **skippé** : sans gravité.
   **Limite (faux négatif)** : si un fichier est modifié mais que son `mtime` apparaît **en retard** (flush tardif, NFS, horloge), il peut tomber **sous** le curseur et n'être **jamais ré-énuméré** → le `content_hash` ne tourne pas (le fichier n'est pas regardé). Mitigation : **fenêtre de recouvrement** — `new_cursor = max(lastModified) − OVERLAP` (ex. 5 min). On ré-examine systématiquement les items récents ; s'ils sont inchangés, le dedup les skippe (coût négligeable). `content_hash` **ne suffit pas** seul ; l'overlap couvre le faux négatif.

2. **Suppressions = différence, donc complétude obligatoire.** Sans diff, `deleted` = *« dans `indexed_documents` mais absent de l'énumération courante »* → `enumerate()` doit être **complet ou lever** (garantie `19`), sinon faux deletes.

### Identité (`id`) vs affichage (`title`)

`ItemRef` porte **deux** champs distincts — à poser ici car le moteur les utilise séparément :
- **`id`** = identité **stable** → sert de **clé de stockage** (`indexed_documents.path`, et le `path` des chunks) **et** de clé de détection des suppressions. Doit **survivre aux renommages**.
- **`title`** = libellé **humain** → `indexed_documents.title` (colonne existante), affiché dans les résultats de recherche / `get_document` (`18`).

Pour `folder` : `id = title = chemin relatif` (confondus). Pour une source REST (`21`) : `id` = identifiant distant **stable**, `title` = libellé lisible extrait de la réponse. **Conséquence** : la clé de stockage n'est pas toujours « lisible » → les surfaces (`18`) **affichent `title`** quand il est présent, jamais l'`id` brut.

### Point critique — scoper la différence **par source**

`indexed_documents` n'a **pas** de `source_id` aujourd'hui. Sur un workspace **multi-sources** (git + folder), la différence de `folder` verrait **tous les fichiers git** comme « absents de mon énumération » → **faux deletes massifs**. Correctif propre (option retenue) : **ajouter `indexed_documents.source_id`** (migration) et **scoper `load_indexed_paths` par `source_id`**. Les autres options — préfixe de chemin (fragile, git/folder peuvent partager des préfixes) ou « V1 = une seule source par workspace » (limitation qui mordra) — sont écartées au profit de la correction durable.

## L'adaptateur `folder`

La source la plus simple du profil — pur mécanisme :

- **config** (déclaratif, `workspace_sources.config`) : chemin d'un dossier **monté en volume**.
- **`enumerate()`** : parcours du dossier → `ItemRef(id=chemin_relatif_à_la_racine, title=chemin_relatif, last_modified=mtime)` par fichier (pour folder, `id` et `title` coïncident). L'`id` est **relatif à la racine déclarée** → stable même si le volume est remonté ailleurs.
- **`fetch_content(unit)`** : lecture du fichier en texte (skip binaire, comme git).
- **cursor** : `{"last_modified": "<iso>"}`.
- **Invariant de déploiement** (à documenter) : la **racine configurée** doit rester **stable** entre deux runs. Si elle change, tous les `id` changent → la différence voit tout comme supprimé+ajouté. L'`id` relatif protège du *remontage* du volume ; il ne protège pas d'un changement de **racine logique** dans la config.

### Énumération complète vs incrémentale (pour sources coûteuses)

Par défaut, `enumerate()` est **complète à chaque run** (nécessaire aux suppressions par différence) — négligeable pour `folder`. Pour une source **coûteuse / rate-limitée** (source REST distante, S3), la primitive **autorise une variante** : un couple `enumerate_changes_since(cursor)` (incrémental, borné aux récents) + `enumerate_all()` (complet, exécuté sur une **cadence** `full_scan_interval`, pas à chaque run). Les **changements** restent fréquents et bornés ; la **détection de suppression** (full scan) devient périodique. `folder` n'a pas besoin de cette variante ; `21` l'utilise.

Aucune auth, aucune normalisation : exactement le but. Folder est aussi sur la roadmap — donc utile en soi, pas qu'un banc d'essai.

## Webhook = optimisation (réaffirmation de `19`)

Un webhook (s'il existe pour une source) ne fait que **déclencher un `changes_since` plus tôt**. La **garantie de complétude** vient toujours du balayage (curseur + énumération). Webhooks ratés → le prochain poll rattrape. Le webhook n'est jamais une voie parallèle qui contournerait le curseur.

## Performance (honnête)

L'énumération **complète à chaque run** est nécessaire pour détecter les suppressions par différence. Pour `folder` c'est un walk de répertoire (négligeable). Pour de très grosses sources (`21`/S3), ce coût devient réel → une **détection de suppression périodique** (pas à chaque run) sera une optimisation possible, **différée** : V1 = énumération complète pour la correction. À mesurer (harness `22`).

## Migrations

- **Config** : `indexed_documents.source_id UUID REFERENCES workspace_sources(id) ON DELETE CASCADE` (additive) — **nécessaire à la correction** de la différence multi-sources. Backfill : les lignes existantes → l'unique source de leur workspace (cas mono-source actuel ; aucun folder n'existe encore). Le moteur (`19`) renseigne `source_id` à chaque `index_file`/`_record_indexed_document`.
- `cursor` existe déjà (`19`) ; la config `folder` vit dans `workspace_sources.config`.
- **Déploiement** : le dossier source doit être **monté en volume** dans le conteneur, à une **racine stable** (cf. invariant).

## Tâches (TDD)

- [ ] **Migration `indexed_documents.source_id`** + backfill ; le moteur (`19`) renseigne `source_id` à chaque indexation.
- [ ] `ItemRef` (id **stable** = clé stockage/suppression, title = affichage, last_modified) ; `ReconstructedCursorSource(Source)` avec `changes_since` générique (énum complète → added/modified/deleted → `new_cursor = max(last_modified) − OVERLAP`, `cursor=None` → tout candidat) ; variante `enumerate_changes_since`/`enumerate_all` + `full_scan_interval` pour sources coûteuses.
- [ ] `load_indexed_paths(workspace, source_id)` **scopé par source** depuis `indexed_documents`.
- [ ] `OVERLAP` configurable (défaut ~5 min) ; documenter le compromis (re-fetch redondant skippé par dedup).
- [ ] Garantie : `enumerate()` partielle/échouée → **lève**, curseur non avancé (cf. `19`).
- [ ] `FolderSource(ReconstructedCursorSource)` : `enumerate` (walk + mtime, id relatif), `fetch_content` (read). Registry `folder`.
- [ ] Tests : add/modif/suppression reflétés ; `touch` → skip dedup ; **mtime en retard < overlap → re-vu** ; énumération partielle → aucun faux delete ; **workspace git+folder → pas de faux delete croisé**.
- [ ] Context7 avant code.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts.
2. `ReconstructedCursorSource.changes_since` respecte les **3 garanties de `19`** (curseur atomique en fin de `done`, delta complet ou lève, contenu via `fetch_content`).
3. `FolderSource` ne contient **que** `enumerate` + `fetch_content` (toute la logique de delta est dans la primitive).
4. Context7 consulté.

### Critères fonctionnels
5. Un workspace `type=folder` pointant un dossier monté indexe son contenu (premier run = tout, `cursor` NULL géré).
6. Modifier → réindexé ; supprimer → suppression propagée (par différence **scopée source**) ; ajouter → indexé.
7. `touch` sans changement de contenu → re-fetch mais **skip** par dedup `content_hash` ; un fichier au `mtime` **en retard mais dans l'overlap** est **ré-examiné** (pas de faux négatif).
8. Énumération partielle → **lève**, curseur inchangé, **aucun faux delete**. Sur un workspace **git + folder**, la sync folder ne supprime **jamais** les docs git (différence scopée par `source_id`).

### Scénario de manipulation (recette de démonstration)
1. Monter un dossier `~/notes` en volume, créer un workspace `type=folder` dessus → première sync indexe tous les `.md`.
2. `index_status()` → `cursor = {last_modified: …}` ; relancer sans rien changer → delta vide.
3. Éditer un fichier → seul lui est réindexé. Supprimer un fichier → il disparaît de l'index (déduit par différence, sans diff). Ajouter un fichier → indexé.
4. `touch` un fichier inchangé → la trace montre un re-fetch mais un **skip dedup** (le `content_hash` est identique) : le `lastModified` peu fiable ne pollue pas l'index.
5. Simuler une énumération partielle (dossier momentanément inaccessible) → le job **lève**, le curseur ne bouge pas, rien n'est supprimé à tort.

**Ce que ça apporte.** Le rag sait désormais ingérer **n'importe quelle source sans journal** — la mécanique dure (delta reconstruit, suppressions par différence, robustesse au `lastModified`) est écrite **une fois**, prouvée sur le cas le plus simple. `folder` est livré au passage. Et `21` (source REST) ne sera plus que : *appeler l'opération de listing + extraire le contenu de la réponse* — posés sur une primitive déjà sûre.

## Notes / décisions ouvertes

- **Scoping par `source_id`** : **tranché** — migration `indexed_documents.source_id` + différence scopée. Corrige le faux-delete multi-sources (bug réel sinon).
- **Overlap (clock skew)** : `new_cursor = max(lastModified) − OVERLAP` ; couvre le **faux négatif** (mtime en retard) que `content_hash` seul ne couvre pas. `OVERLAP` configurable (défaut ~5 min). À confirmer la valeur.
- **`cursor=None`** (1ᵉʳ run) : tout est candidat ; géré explicitement.
- **`ItemRef.id` relatif à la racine** : stable au remontage du volume ; **invariant** = racine logique stable dans la config (documenté).
- **Split added vs modified** : déduit par présence dans `prev` (`indexed_documents` scopé source). Sans importance fonctionnelle ; logging.
- **Énumération complète à chaque run** : correct mais coûteux sur grosses sources → détection de suppression périodique en optimisation **différée** (`21`/S3).
- **`ItemRef` id vs title** : **tranché** — `id` = identité stable (clé de stockage `indexed_documents.path` + détection des suppressions), `title` = libellé humain (`indexed_documents.title`, affiché). folder : confondus ; source REST : `id` = identifiant distant, `title` = libellé extrait de la réponse.
- **Variante incrémentale + full-scan périodique** : disponible pour sources coûteuses (`full_scan_interval`) ; `21` l'utilise pour tenir le rate-limit d'une API distante.
