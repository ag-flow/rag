# 21 — Source REST générique (contrat OpenAPI)

> **Disclaimer.** Dernier des trois chantiers sources ; dépend de `19` (interface) **et** `20` (primitive curseur reconstruit). **Aucun client vendeur** : on ne code pas un connecteur par fournisseur, on consomme une **API REST quelconque** via un mécanisme d'appel HTTP configurable — le **même** que le moteur d'automatisation (import OpenAPI, `body_template`, `automation_header`, `secret_ref`, substitution JSON-safe). Avant d'implémenter, **revérifie** : le stockage des contrats OpenAPI importés (à **réutiliser**, pas réinventer), le resolver de secrets (`_resolve_token`/`${vault://…}`), le point d'extension des webhooks entrants. **Context7**, **Serena**, skill **`brainstorming`**. Le **mapping réponse→contenu indexable** et le **profil de complétude** sont les deux vrais sujets.

## Position dans la série

3ᵉ et dernier du chantier sources. Posé sur `20`, cet adaptateur **n'implémente que** l'énumération et la récupération via des **appels REST configurés** ; tout le reste — delta reconstruit, suppressions par différence **scopée source**, overlap clock-skew, robustesse `content_hash`, `id`/`title`, variante full-scan périodique — est **hérité**.

## Rôle

Ingérer **n'importe quelle source distante exposant une API REST**, sans écrire de code spécifique au fournisseur. Le paramétrage est **piloté par contrat OpenAPI** + configuration d'appels — réutilisant le mécanisme du moteur d'automatisation. **Modèle A (ingestion)** : le rag tire le contenu et lui applique **son** pipeline (chunking, enrichissement, hybride, recherche unifiée), au lieu de déléguer la recherche à la source.

## Hérité de `20` (gratuit)

`changes_since` (delta reconstruit), suppressions par différence scopée `source_id`, overlap, dedup `content_hash`, `id` (stable) / `title` (affichage), variante `enumerate_changes_since` + `enumerate_all` cadencée (`full_scan_interval`). **L'adaptateur n'y touche pas.**

## Paramétrage en deux temps

1. **Importer le contrat OpenAPI** → récupérer la liste des **opérations distantes** disponibles (réutilise le stockage/mécanisme du moteur d'automatisation : `openapi_ref`).
2. **Configurer les appels** dont la source a besoin (rôles `list`, `fetch`, et parse `webhook`), chacun avec : `url`, `http_method`, `body_template`, `automation_header`.

### § Contrat OpenAPI (ce qu'il apporte)

- Un **squelette de body prérempli** depuis le schéma de l'opération.
- La **liste des headers attendus** (obligatoires vs facultatifs).
- Le formulaire **présente** les champs mais **ne valide pas** le contenu — **délibéré**.
- **Hors V1** : validation du schéma de body (l'utilisateur en est responsable) ; auth déclarée dans le contrat OpenAPI (les headers d'auth sont ajoutés **manuellement**).

### § Variables & substitution

- `body_template` : JSON éditable manuellement, où l'utilisateur place des variables (`{id}`, `{cursor}`, …).
- **Substitution JSON-safe obligatoire** : `json.dumps` de **chaque valeur** (pas un `str.replace` brut) — sinon un guillemet dans une valeur casse le body.
- Variables résolues sur la **version courante au moment de l'exécution**, pas au déclenchement.
- `automation_header` : headers libres ; chaque header est une valeur **en clair** ou une **`secret_ref`** résolue depuis le coffre (Harpocrate) **à l'exécution**, jamais stockée en clair.

### § Exécution (déroulé d'un appel)

1. Résoudre les `secret_ref` des headers au coffre (à l'exécution).
2. Substituer les variables **JSON-safe** dans `url`/`body_template`.
3. Émettre `http_method` + `url` + headers + body.
4. **Extraire** de la réponse ce qui nous intéresse (ci-dessous) — c'est l'**inverse** du `body_template` (sortant) : un mapping **entrant** réponse→données.

## Mapping réponse→indexable (le pendant ingestion)

Le moteur d'automatisation est **sortant** (il pousse un `body_template`). Ici on **ingère** : il faut donc des **extracteurs de réponse** (chemins type JSONPath), par rôle :

- **`list`** → un tableau d'items : `items_path` (le tableau), puis par item `id_path`, `last_modified_path`, `title_path`. Alimente l'`enumerate_all()` de `20` (`id`/`title`/`last_modified`).
- **`fetch`** → le contenu d'un item : `content_path` + `content_format` (`text` | `markdown` | `html`). Alimente `fetch_content()`.

### Normalisation du contenu

`content_format` déclare le format extrait. `text`/`markdown` → passe tel quel au chunker (le markdown réutilise le chunker markdown existant). `html` → **normalisation générique HTML→markdown** avec **dégradation gracieuse** : un élément/balise inconnu est dégradé (texte brut) ou ignoré, **jamais** une exception — un fragment non géré ne bloque **jamais** l'indexation d'un document entier. Imperfection acceptable (retrieval, pas reproduction fidèle), non gérés **loggés**.

## Le carrefour complétude — profil A par défaut, B en repli

C'est la décision structurante. « Pas de système distant capable de lister ce qui a *bougé* » est **compatible** avec `20` : le curseur reconstruit n'interroge jamais un flux de changements — il **énumère** et fait la **différence**.

- **Profil A — énumération conservée (défaut, dès qu'une opération de listing existe).** Le rôle `list` sert d'`enumerate_all()` → la primitive `20` s'applique **telle quelle** : delta reconstruit, **suppressions par différence**, full-scan périodique (`full_scan_interval`). Le **webhook = optimisation de réactivité**. Les garanties `19`/`20` **tiennent**.
- **Profil B — webhook-pur (repli assumé, uniquement si l'API n'offre que du fetch-by-id).** Aucune énumération : changements **et** suppressions ne sont appris que par les **events webhook**. **Best-effort** : un webhook raté = un trou silencieux ; une suppression n'est détectée **que si** la source émet un event `deleted`. C'est exactement le mode d'échec contre lequel `19`/`20` ont été conçus → **documenté comme dégradé**, choisi seulement faute de listing.

Le profil **découle** de la présence d'un rôle `list` configuré : présent → A ; absent → B.

## Réveil par webhook (config-driven)

On **consomme la gestion des hooks** existante. Le payload entrant est parsé par **configuration** (pas de code par fournisseur) : `event_path` (type d'event), `id_path` (item concerné), `deleted_event` (valeur signalant une suppression).
- **Profil A** : le webhook déclenche un cycle **incrémental** (pas un full scan) — réactivité ; le full scan reste cadencé.
- **Profil B** : le webhook est la **seule** source de changements/suppressions.

## Coût & rate-limit (rappel de `20`)

`enumerate_changes_since` (incrémental, via `{cursor}`/`{since}` dans la `list` **si l'API filtre par date**, sinon repli full) reste borné. `enumerate_all` (full scan, pour les suppressions) tourne sur `full_scan_interval`, **pas à chaque run** → on évite qu'une API rate-limitée fasse échouer/relancer indéfiniment un gros scan. Respect du `Retry-After`/backoff sur toute énumération.

## Config (`workspace_sources.config`) — générique

```json
{
  "type": "rest",
  "openapi_ref": "<contrat importé>",
  "operations": {
    "list":  { "operation_id": "...", "url": "...", "http_method": "GET",
               "body_template": null,
               "automation_header": [{ "name": "Authorization", "secret_ref": "${vault://harpocrate-1:/…}" }],
               "pagination": { "next_cursor_path": "$.next" },
               "response": { "items_path": "$.items", "id_path": "id",
                             "last_modified_path": "updated_at", "title_path": "name" } },
    "fetch": { "operation_id": "...", "url": ".../{id}", "http_method": "GET",
               "automation_header": [{ "name": "Authorization", "secret_ref": "${vault://harpocrate-1:/…}" }],
               "response": { "content_path": "$.body", "content_format": "html" } },
    "webhook": { "event_path": "$.event", "id_path": "$.id", "deleted_event": "removed" }
  },
  "full_scan_interval": "24h"
}
```

## Migrations

- **Aucune** : `cursor` (`19`), `indexed_documents.source_id` (`20`), `config` JSONB existent. Le contrat OpenAPI **réutilise le stockage du moteur d'automatisation** (`openapi_ref`) — à confirmer, ne pas dupliquer. Registry : type `rest`.

## Tâches (TDD)

- [ ] `RestSource(ReconstructedCursorSource)` : `enumerate_all()` = appel `list` (paginé via `pagination.next_cursor_path`) → items mappés (`id`/`title`/`last_modified`) ; `enumerate_changes_since` = `list` filtré `{cursor}` si possible, sinon repli full ; `fetch_content` = appel `fetch` `{id}` → extraction `content_path` + normalisation `content_format`.
- [ ] Profil **A si `list` configuré, B sinon** (webhook-pur dégradé, documenté).
- [ ] Moteur d'appel HTTP : substitution **JSON-safe** (`json.dumps` par valeur), `automation_header` clair/`secret_ref` résolu **à l'exécution**, variables sur version courante.
- [ ] Extracteurs réponse (JSONPath-like) `list`/`fetch` ; normalisation `html`→markdown **dégradation gracieuse** (balise inconnue → texte/skip, jamais d'exception ; loggée).
- [ ] Webhook config-driven : `event_path`/`id_path`/`deleted_event` → cycle incrémental (A) ou source unique (B).
- [ ] Réutiliser le stockage de contrat OpenAPI du moteur d'automatisation ; registry `rest`.
- [ ] Backoff `Retry-After` ; `full_scan_interval` respecté.
- [ ] Tests : substitution JSON-safe (guillemet dans une valeur ne casse pas le body) ; `secret_ref` résolue à l'exécution (jamais en clair) ; item modifié → réindexé ; supprimé → delete (par différence en A, par event en B) ; balise html inconnue n'interrompt pas le document.
- [ ] **Context7** (OpenAPI / client HTTP) avant code.

## Definition of Done

### Critères techniques
1. ruff + mypy + tests verts.
2. `RestSource` ne contient **aucun** code spécifique à un fournisseur ; tout passe par le contrat + la config.
3. Substitution **JSON-safe** prouvée (valeur contenant `"` n'invalide pas le body) ; `secret_ref` jamais stockée/loggée en clair, résolue à l'exécution.
4. Profil A : `enumerate_all` **complet ou lève** (garantie `19`/`20`). Context7 consulté.

### Critères fonctionnels
5. Importer un contrat OpenAPI → les opérations distantes sont listées ; configurer `list`+`fetch` → un workspace `type=rest` indexe les items (résultats affichant le **`title`** extrait, pas l'`id` brut).
6. Item modifié à distance → réindexé (incrémental, ou plus tôt via webhook) ; renommé → **pas** de delete+add (`id` distant stable, `title` mis à jour) ; supprimé → propagé (différence au full scan en **A** ; event `deleted` en **B**).
7. Contenu `html` normalisé en markdown exploitable ; une balise/structure inconnue est **dégradée sans interrompre** le document.
8. Sans rôle `list` (API fetch-by-id seule) → profil **B** activé, comportement best-effort **documenté** ; avec `list` → profil **A**, garanties pleines.

### Scénario de manipulation (recette de démonstration)
1. Importer le contrat OpenAPI d'une API distante ; configurer `list` (avec `automation_header` → `secret_ref` coffre) et `fetch` ; créer un workspace `type=rest`.
2. Première sync → les items listés sont récupérés, normalisés, indexés. `index_status()` montre le `cursor`.
3. Dans un cadrage, interroger ce corpus distant → réponses fondées sur le contenu **ingéré**, à côté du code, avec **son** pipeline (hybride/enrichissement).
4. Modifier un item à distance → réindexé ; le renommer → l'index suit **sans** delete+add ; le supprimer → disparaît (au full scan).
5. Mettre une valeur contenant un guillemet dans un champ → le body reste **valide** (JSON-safe). Retirer le rôle `list` → bascule en profil **B** (webhook-pur), signalé comme dégradé.

**Ce que ça apporte.** Le rag ingère **n'importe quelle API REST** sans connecteur vendeur — un mécanisme d'appel **unique et configurable** (OpenAPI + `body_template`/`automation_header`/`secret_ref`), partagé avec le moteur d'automatisation. Grâce à `20`, l'effort se limite à *configurer un listing + extraire le contenu de la réponse* ; la mécanique dure (delta, suppressions, robustesse) était déjà écrite. Et le profil A préserve les garanties là où un listing existe ; B n'est qu'un repli assumé. Le chantier sources est complet : folder, REST et **docflow** (journal natif) suivent la même interface.

## Notes / décisions ouvertes

- **A/B** : tranché — A dès qu'un rôle `list` existe ; B (webhook-pur, dégradé) en repli pour les API fetch-by-id seules.
- **Extracteurs réponse** : JSONPath-like (`items_path`/`id_path`/`content_path`…). Choisir la lib (Context7) ; gérer les chemins absents proprement (item ignoré + log, pas de crash).
- **`content_format=html`** : normalisation générique + dégradation gracieuse. XML/autres formats → étendre à la demande.
- **Réutilisation du moteur d'automatisation** : le mécanisme d'import OpenAPI + config d'appel **ne doit pas être dupliqué** — à mutualiser. Vérifier où il vit (docflow/devpod) et comment le partager côté rag.
- **`enumerate_changes_since` incrémental** : possible seulement si la `list` accepte un filtre date (`{cursor}`) ; sinon repli full à chaque run (acceptable pour petites sources).
- **docflow comme source** (journal natif) : symétrique et trivial sur cette interface — expose son `change_log`, zéro reconstruction. Sujet « connecteur docflow→rag » encore non évalué.
