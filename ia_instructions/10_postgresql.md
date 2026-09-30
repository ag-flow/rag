# PostgreSQL — ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — spécificités
> PostgreSQL » (révision 2026-09-24). À lire AVANT d'écrire une migration ou une requête SQL.

### État en base

- Migrations = fichiers **numérotés immuables**. Une migration appliquée ne s'édite JAMAIS : elle est déjà jouée ailleurs, la corriger fait diverger les bases
- Réconciliation **additive** : ajouter une colonne nullable est automatique ; renommer ou supprimer exige une migration explicite, relue
- Requêtes **toujours paramétrées**. Une f-string dans du SQL est une faute, pas un raccourci
- Une opération de cycle de vie = **une** transaction
- Les invariants qu'un DDL ne sait pas exprimer sont validés applicativement **et testés**

### Deux séries de migrations

- **Base de config** (`rag_config`) : `backend/migrations/NNN_nom.sql`, appliquées par
  `rag.db.migrations.run_migrations` au démarrage du backend.
- **Bases de workspace** (`rag_<workspace>`) : `backend/src/rag/db/workspace_migrations/versions/`,
  rejouées au démarrage sur **toutes** les bases de workspace (`apply_pending_for_all_workspaces`,
  fail-fast). Une migration de workspace doit donc passer sur des bases d'âges différents.
- Toute nouvelle table → migration SQL **+ test de migration**.

**Exception assumée** : un identifiant DDL (`CREATE DATABASE "rag_<nom>"`) ne se paramètre pas
avec asyncpg. Il est interpolé **quoté**, et seulement après validation du nom par regex
(`schemas/admin.py`). Aucune autre interpolation dans du SQL.

### Pièges connus

**Une violation de contrainte avorte la transaction entière.** Sur PostgreSQL, un `INSERT` en conflit ne se rattrape pas par un simple `try/except` si la transaction doit continuer : il faut un point de sauvegarde (`SAVEPOINT` / `begin_nested`). C'est décisif quand le conflit est le cas **normal** — une idempotence portée par une contrainte d'unicité, par exemple.

**L'idempotence se joue à l'écriture, jamais par une lecture préalable.** Entre un `SELECT` et un `INSERT`, deux appels concurrents passent tous les deux. On insère, et c'est la base qui tranche.

**Vérifier une migration sur une base vierge ET sur une base existante.** Une migration qui ne passe que sur l'une des deux se découvre en production.

**Un numéro de migration se collisionne dès qu'on travaille à plusieurs.** Vérifier le dernier numéro réellement présent avant d'en créer un — pas celui qu'on croit se rappeler.

**Une table peut déjà exister.** Avant d'en créer une, chercher son nom dans les migrations et le schéma : trouver une table écrite il y a longtemps et jamais appelée est plus fréquent qu'on ne le croit.

### Part de checklist PostgreSQL

- [ ] La migration ajoutée porte un numéro libre, vérifié contre l'existant
- [ ] Elle rejoue sur base vierge **et** sur base existante
- [ ] Aucune migration déjà appliquée n'a été modifiée
- [ ] Aucune requête construite par concaténation ou f-string
- [ ] Le nom de toute table ou colonne ajoutée a été cherché avant, pour ne pas doubler l'existant
