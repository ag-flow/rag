# Python — backend ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — spécificités Python »
> (révision 2026-09-24). À lire AVANT de modifier un fichier `.py`.

### Conventions Python

- Python 3.12+, async/await partout — **jamais** de `subprocess.run` ni d'I/O bloquant dans
  un chemin asynchrone
- pydantic v2, `extra="forbid"` sur tous les modèles de configuration
- `structlog.get_logger(__name__)` — **jamais** `print()`. Un secret ne se déballe qu'au
  point d'injection
- `from __future__ import annotations` en tête de fichier, annotations de type partout
- Fichiers max 300 lignes ; une classe = une responsabilité ; méthodes de 5 à 15 lignes
- Entrées utilisateur validées par regex stricte AVANT tout usage en chemin, identifiant ou
  nom d'hôte — la concaténation de chaînes est une faute

### Nommage Python

| Élément | Convention |
|---|---|
| Fichiers, fonctions, variables | `snake_case` |
| Classes | `PascalCase` |
| Constantes | `UPPER_SNAKE` |
| Privé | préfixe `_` |

**Préfixer selon la SOURCE de la donnée** — c'est ce qui dit, au nom seul, ce qu'une
méthode touche et donc comment la tester :

| Préfixe | Ce que la méthode fait |
|---|---|
| `db_` | lit ou écrit en base |
| `file_` | lit ou écrit un fichier |
| `resolve_` | orchestre les deux, et décide |

Le nom dit ce que la fonction **fait**, pas comment : `resolve_agent_avatar()`, pas
`process()` ni `handle()`.

### Erreurs en Python

- **Aucun repli silencieux.** Une valeur par défaut qui masque une donnée manquante
  transforme un bug en comportement, et le symptôme apparaît loin de sa cause.
  `state.get("team_id", "team1")` est une faute ; exiger la donnée et lever sinon.
- **Aucun `except` nu ni `except: pass`.** Attraper une exception précise, journaliser le
  contexte, et relancer si l'appelant doit savoir.
- **Les erreurs se traitent à la frontière**, pas au milieu : la couche qui peut décider
  quoi faire les attrape, les autres les laissent passer.
- Aucune constante magique dans le code : une valeur qui décide se nomme.

### ⚠ Écarts constatés avec le code existant — à trancher par l'architecte

- `rag.config.Settings` est en `extra="ignore"`, pas `"forbid"` : le `.env` est partagé avec
  docker compose (`POSTGRES_*`, `LOKI_URL`…) que les Settings ne déclarent pas. Ne pas le
  passer en `forbid` sans décision : le backend refuserait de démarrer. Les DTOs de
  `schemas/`, eux, suivent la règle.
- Le préfixage par source (`db_` / `file_` / `resolve_`) n'est pas appliqué dans le code
  existant. Il s'applique au code **nouveau** ; ne pas renommer l'existant hors chantier dédié.

### Tests Python

Cadre : **pytest** + **pytest-asyncio** (`asyncio_mode = "auto"`). Fixtures partagées dans
`backend/tests/conftest.py` (dont `pg_container` : base jetable `rag_test_<uuid>` sur le
Postgres pointé par `TEST_POSTGRES_*`). Fichiers temporaires via `tmp_path`, jamais le dépôt.
Chaque accès base est testé **dont le cas « rien trouvé »** ; chaque flux par un test complet
plus ses branches d'arrêt. Récursivité : profondeur 0, 1, maximale (erreur **rendue**, jamais
un débordement de pile) et données circulaires.

```bash
cd backend && uv run pytest tests/unit -q          # unitaires, sans réseau
cd backend && uv run pytest -q                     # tout sauf smoke (Postgres requis)
cd backend && uv run pytest -m smoke -v            # providers réels, opt-in
cd backend && uv run pytest --cov=src/rag --cov-report=xml   # rapport pour l'analyse statique
cd backend && uv run ruff check src tests
cd backend && uv run ruff format --check <fichiers du chantier>
cd backend && uv run mypy src/rag                  # strict
```

Journalisation : `structlog.get_logger(__name__)`, jamais `print()`.

### Pièges connus

**`extra="forbid"` n'est pas décoratif.** Sans lui, une clef de configuration mal orthographiée est ignorée en silence et le défaut s'applique — le symptôme apparaît en production, loin de sa cause.

**`from __future__ import annotations` change le sens des annotations** : elles deviennent des chaînes. Ce qui les lit à l'exécution — pydantic, certains décorateurs — doit pouvoir les résoudre ; un type importé sous `if TYPE_CHECKING:` ne le sera pas.

**`structlog` réserve la clef `event`** pour le message. `log.info("truc", event=x)` lève un `TypeError` **à l'exécution** et jamais au lint.

**Le formateur n'est pas le linter.** `ruff check` et `ruff format` sont deux commandes ; passer l'une ne dit rien de l'autre.

**Une violation de contrainte en base avorte la transaction entière** — voir l'enfant PostgreSQL, ce n'est pas un piège Python mais il se manifeste ici.

### Part de checklist Python

- [ ] `ruff check`, `ruff format --check` et `mypy` passent sur le périmètre modifié
- [ ] Aucun I/O bloquant introduit dans un chemin asynchrone
- [ ] Les modèles de configuration ajoutés portent `extra="forbid"`
- [ ] Aucun repli silencieux, aucun `except` nu ajouté
- [ ] Les méthodes ajoutées portent le préfixe de leur source, et sont testées en conséquence
- [ ] Les entrées utilisateur nouvelles sont validées avant tout usage en chemin ou identifiant
