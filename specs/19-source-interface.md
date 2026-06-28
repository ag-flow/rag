# 19 — Interface `Source` (extraction depuis git)

> **Disclaimer.** Écrite à partir du sync worker réel (`sync/executor.py::_execute_git_job`, `sync/git_ops.py`, `workspace_sources`, `index_jobs`). **Verdict de l'audit : git est câblé en dur** — aucune abstraction `Source`, aucun dispatch par `type`. Avant d'implémenter, **réévalue les impacts** et **revérifie** : où le curseur (`last_commit`) est réellement persisté aujourd'hui, le contrat exact de `diff_changes`/`ChangeSet`, les étapes génériques vs git. **Context7**, **Serena** (cartographier `_execute_git_job` ligne 606+), skill **`brainstorming`**. C'est un **refactor à comportement constant** : la barre, c'est « git indexe exactement comme avant ».

## Position dans la série

Premier des **trois** chantiers issus de « Source + curseur reconstruit + source REST » (découpe assumée, scope trop large pour une spec) :
- **19 (ici)** — extraire l'interface `Source`, git comme 1ʳᵉ implémentation (profil *journal natif*). Refactor zéro-comportement.
- **20** — primitive *curseur reconstruit* + adaptateur `folder` (mécanisme pur).
- **21** — source REST générique pilotée par contrat OpenAPI (import, appels, extraction).

19 est la **fondation** : sans elle, 20 et 21 n'ont rien où se brancher.

## Rôle

Séparer **ce qui est propre à une source** (« qu'est-ce qui a changé depuis mon dernier passage ? », « donne-moi le contenu de cette unité ») de **ce qui est générique** (filtrer, dédupliquer, indexer, supprimer, enrichir, gérer les jobs). Aujourd'hui les deux sont **mélangés** dans `_execute_git_job`. On extrait l'interface, et **git devient la première implémentation** — sans rien changer à son comportement.

## Le contrat `Source` (ancré sur le code réel)

```python
class Source(Protocol):
    async def changes_since(self, cursor: Cursor | None) -> ChangeDelta: ...
    async def fetch_content(self, unit: ChangedUnit) -> str | None: ...

# ChangeDelta = (units: ChangeSet{added, modified, deleted}, new_cursor: Cursor)
```

- **`changes_since(cursor)`** : rend les unités changées **et** le nouveau curseur. C'est la seule chose qui varie entre sources.
- **`fetch_content(unit)`** : rend le contenu **normalisé** (texte) d'une unité. Pour git, lecture du fichier dans le checkout ; pour une source REST (`21`), extraction du contenu de la réponse distante. *(Le contenu peut être livré avec l'unité quand la source l'a déjà — détail d'implémentation, cf. note.)*

**Deux profils** (le contrat est le même, l'implémentation diffère) :
- **journal natif** (git, et plus tard docflow) : la source *sait* dire son delta. Curseur = SHA ; `changes_since` = `diff_changes(last_commit → head_commit)`. **Implémenté ici.**
- **curseur reconstruit** (folder, source REST, S3) : la source ne sait pas → le rag fabrique le delta par balayage `lastModified > cursor`. **Implémenté en `20`.**

### Garanties du contrat (ce dont `20`/`21` héritent)

Ces règles sont triviales pour git (HEAD atomique) mais **critiques** pour les sources reconstruites — les poser ici évite que `20`/`21` héritent d'un silence qui devient un bug.

- **Atomicité du curseur** : le moteur écrit `new_cursor` **uniquement en fin de job `done`**, en une écriture atomique. Job `error` → curseur **inchangé**, le prochain run rejoue le même delta. **Jamais** d'avance de curseur sur un job partiel (sinon les unités non traitées ne seraient jamais réindexées).
- **Complétude du delta** : `changes_since` rend un delta **complet** ou **lève**. Un `new_cursor` n'est valide **que si** `units` est exhaustif. **Interdit** : rendre un delta partiel (timeout, FS inaccessible) *avec* un curseur avancé.
- **Point de contrat unique pour le contenu** : le moteur appelle **toujours** `fetch_content(unit)` et ne lit **jamais** `unit.content` en direct. Une `ChangedUnit` *peut* porter son contenu (livré par `changes_since`) ; `fetch_content` le renvoie alors immédiatement, sinon il va le chercher. Un seul chemin → pas de divergence entre adaptateurs.

## Ce qui est générique (le moteur de sync partagé, à extraire)

Tout ceci, aujourd'hui dans `_execute_git_job`, devient le **moteur** qui consomme n'importe quelle `Source` :
- `filter_glob(changes, include, exclude)` ;
- dédup via `indexed_documents.content_hash` (skip si inchangé) ;
- `index_file(...)` (+ `extra_metadata` de `17`) ;
- suppressions (`changes.deleted` → `delete_file`) ;
- enrichissement (`run_enrichments`) ;
- jobs / erreurs / retry / reschedule (`index_jobs`, `_mark_job_error`, `_reschedule_job`) ;
- `.rag/strategy.yml` → **décidé : git-spécifique**. Lu **dans `GitSource`** (c'est un fichier du repo), transparent pour le moteur — pas une méthode du protocole `Source`. (Une source non-git n'a pas de `.rag/strategy.yml`.)

## Ce qui est spécifique git (à isoler derrière `GitSource`)

- clone/pull + checkout local (`repo_storage`) ;
- `head_commit` (curseur), `diff_changes`/`list_all_files` (delta) ;
- lecture fichier (contenu), auth token/SSH (`auth_type`, `ssh_*`).

→ `GitSource` implémente `Source` (profil journal natif). `_execute_git_job` devient *« charger la source du type voulu → moteur générique »*.

## Le curseur, enfin explicite (et deux smells à nettoyer)

État réel vérifié — le curseur git **est déjà persisté**, mais mal rangé, et il est **dupliqué** :
- **Source de vérité** : `workspace_sources.config.last_commit` (lu ligne 630, écrit ligne 795). Or `config` est le JSONB **déclaratif** (URL, branche, auth) → y stocker de l'**état mutable** (le curseur) est un **smell** : on mélange entrée déclarative et état runtime.
- **Doublon** : `index_jobs.correlation_id` est aussi écrasé avec le SHA (ligne 704) — détournement d'un champ censé être un ID de corrélation. **Second smell.**

Le refactor nettoie **les deux** en donnant au curseur un home propre :
- **`workspace_sources.cursor JSONB`** (NULL au départ) — opaque, son contenu appartient à la source (git : `{"sha": "…"}` ; folder/REST : `{"last_modified": "…"}`). État runtime **séparé** de la config déclarative.
- Le git path **cesse** d'écrire `config.last_commit` et **cesse** de surcharger `correlation_id` avec le SHA (qui redevient un pur ID de corrélation).
- C'est aussi le `cursor` que `index_status` (`18`) avait **déféré** : matérialisé ici, `index_status.sync` peut l'exposer.

## Dispatch par type

`executor` route sur `workspace_sources.type` → implémentation `Source` via un petit **registry** `{ "git": GitSource }`. Aujourd'hui de facto git ; demain `folder`/`rest` s'ajoutent sans toucher le moteur.

## Migrations

- **Config** : `workspace_sources.cursor JSONB` (additive). **Backfill** : initialiser depuis `config.last_commit` **existant** (la vraie source de vérité actuelle, **pas** `correlation_id`) → `cursor = {"sha": <config.last_commit>}`. Sources sans `last_commit` → `cursor = NULL` (premier run = full, déjà géré par le dedup).
- Après backfill : le code git **arrête** d'écrire `config.last_commit` et la surcharge SHA de `correlation_id` (les deux smells disparaissent).

## Tâches (TDD)

- [ ] Définir `Source` (Protocol), `Cursor`, `ChangedUnit` (avec `content` optionnel), `ChangeDelta` + **garanties** (atomicité curseur, complétude delta, point de contrat `fetch_content`).
- [ ] Extraire `GitSource` (clone/pull, `changes_since` = diff/head, `fetch_content` = lecture checkout, auth, **`.rag/strategy.yml`**) — **sans changer le comportement**.
- [ ] Extraire le **moteur générique** (filter, dedup, index, delete, enrichment, jobs) consommant une `Source` ; écriture du curseur **atomique en fin de job `done`** uniquement.
- [ ] Registry de types + dispatch dans `executor` ; `workspace_sources.cursor` lu/écrit par le moteur.
- [ ] Migration `cursor` + backfill **depuis `config.last_commit`** ; supprimer les écritures `config.last_commit` et SHA-dans-`correlation_id`.
- [ ] **Non-régression git** : un job git produit exactement les mêmes indexations/skips/suppressions/jobs qu'avant (tests de comparaison), curseur inchangé sur job en erreur.
- [ ] Context7 avant refactor.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts ; migration `cursor` appliquée + backfill.
2. `GitSource` implémente `Source` ; le moteur ne contient **aucune** mention de git.
3. **Comportement git strictement inchangé** — prouvé par tests de non-régression (mêmes effets qu'avant le refactor, clone frais **et** pull incrémental).
4. Context7 consulté.

### Critères fonctionnels
5. Un workspace avec source git se synchronise comme avant (clone initial = full ; pull = delta ; suppressions propagées ; dedup par hash inchangé).
6. Le curseur git vit dans `workspace_sources.cursor` et est relu au job suivant ; `config.last_commit` et le SHA-dans-`correlation_id` ne sont **plus écrits**.
7. Un job en **erreur** laisse le curseur **inchangé** (le run suivant rejoue le même delta) ; le curseur n'avance qu'en fin de job `done`.
8. Un **type inconnu** dans `workspace_sources.type` échoue **proprement** (erreur claire, pas de crash) ; `index_status.sync` (`18`) expose le `cursor` matérialisé.

### Scénario de manipulation (recette de démonstration)
1. Sur un workspace git existant, lancer une sync → comportement identique à avant (logs `clone/pull/HEAD`, indexations, skips par dedup).
2. Inspecter `workspace_sources.cursor` → le SHA courant y est ; relancer une sync sans changement → delta vide, tout `skipped`.
3. Pousser un commit (1 fichier modifié, 1 supprimé) → seule la modif réindexée, la suppression propagée — **comme avant**.
4. Créer une source de **type inconnu** (`type='stub'`) → job en erreur **claire** (« type de source non supporté »), pas de crash : le dispatch par registry est prouvé.
5. `index_status()` → le bloc `sync` montre maintenant le `cursor`.

**Ce que ça apporte.** Rien de visible pour l'utilisateur — et c'est le but : c'est la **fondation invisible**. Git passe derrière une interface propre, le moteur de sync devient agnostique, et le curseur devient explicite. Résultat : `20` (curseur reconstruit + folder) et `21` (source REST générique) ne seront plus que des **adaptateurs** branchés sur cette interface, sans retoucher le moteur. On a payé une fois la séparation propre ; on l'encaisse sur toutes les sources futures (folder, source REST, S3, et docflow en journal natif).

## Notes / décisions ouvertes

- **`cursor` JSONB vs TEXT** : JSONB retenu (opaque, extensible par profil).
- **Contenu porté par l'unité vs `fetch_content`** : **décidé** — le moteur passe **toujours** par `fetch_content` ; `ChangedUnit.content` optionnel, renvoyé tel quel s'il est là. Cf. garanties du contrat.
- **`.rag/strategy.yml`** : **décidé** — git-spécifique, lu dans `GitSource`, hors protocole.
- **Atomicité / complétude du curseur** : **décidées** dans les garanties du contrat (avance en fin de `done` seulement ; delta complet ou `changes_since` lève).
- **Webhook** (`11-webhooks`) : reste une **optimisation de réactivité** — déclenche un `changes_since` plus tôt, pas une voie parallèle. Réaffirmé en `21`.
- **Smell `correlation_id`** : sa surcharge SHA est supprimée ici ; vérifier qu'aucun autre code ne lit le SHA depuis `correlation_id` (sinon le brancher sur `cursor`).
- **Normalisation du contenu** : `fetch_content` rend du texte ; l'extraction réponse→texte sera le vrai travail de la source REST (`21`).
