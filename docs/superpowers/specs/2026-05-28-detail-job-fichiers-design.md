# Design — détail d'un job au clic (liste des fichiers traités)

**Date** : 2026-05-28
**Statut** : validé (design), en attente revue spec écrit

## Contexte

L'onglet « Jobs » d'un workspace (`WorkspaceJobsTab.tsx`) liste les jobs d'indexation.
Chaque ligne affiche : statut, déclencheur, `N changed / M skipped`, durée, date relative.

Aujourd'hui, seules les lignes de jobs **en erreur** sont cliquables (expansion d'un panneau
montrant `error_message`) — voir `WorkspaceJobsTab.tsx` : `onClick={() => hasError && toggle(id)}`,
`disabled={!hasError}`. Les jobs réussis (`done`) ne sont pas cliquables.

**Besoin** : rendre tous les jobs cliquables pour voir « ce qui a été fait », c'est-à-dire la
**liste des fichiers réellement modifiés** (ajoutés / modifiés / supprimés), en plus des
métadonnées du job.

**Contrainte découverte** : la table `index_jobs` ne stocke que les **compteurs**
(`files_changed`, `files_skipped`) — pas les chemins. L'executor
(`backend/src/rag/sync/executor.py`) connaît les chemins (`ChangeSet.added/modified/deleted`)
mais ne les persiste pas. Il faut donc les persister.

## Décisions validées

1. **Contenu du détail** : métadonnées + liste des fichiers **changés** (added/modified/deleted).
   Les fichiers **ignorés** (hash inchangé) ne sont PAS stockés (volume : ~12581 par job).
2. **Stockage** : table dédiée `index_job_files` (et non JSONB sur `index_jobs`) — requêtable,
   paginable, propre ; un 1er sync peut produire des milliers de lignes.
3. **Chargement** : à la demande (lazy) au clic, via un endpoint dédié — pas inclus dans la
   liste des jobs (qui peut compter des centaines d'entrées).
4. **Rétroactif** : impossible. Les jobs déjà exécutés n'ont pas de fichiers stockés → leur
   panneau montre les métadonnées + « aucun détail de fichier (job antérieur) ». Seuls les
   nouveaux jobs auront la liste. Accepté.
5. **Volume 1er sync** : l'endpoint limite l'affichage (1000 fichiers) + renvoie le total.

## Architecture

### 1. Migration — `backend/migrations/017_index_job_files.sql`

```sql
-- Migration 017 — fichiers traités par job (pour le détail "ce qui a été fait")
CREATE TABLE index_job_files (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID NOT NULL REFERENCES index_jobs(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('added', 'modified', 'deleted'))
);

CREATE INDEX idx_job_files_job ON index_job_files(job_id);
```

`ON DELETE CASCADE` : si un job est supprimé (via cascade workspace), ses fichiers le sont aussi.

### 2. Executor — `backend/src/rag/sync/executor.py`

Dans la phase « 4. Traite les fichiers » (l. 308-342), collecter les chemins **réellement
traités** avec leur type, en parallèle des compteurs :

- Boucle `changes.added + changes.modified` : quand un fichier est effectivement indexé
  (`files_changed += 1`, pas le cas `skipped`), enregistrer `(path, change_type)` où
  `change_type` = `"added"` si `path in changes.added`, sinon `"modified"`.
- Boucle `changes.deleted` : enregistrer `(path, "deleted")`.

Au passage en `done` (l. 361-376), insérer la liste collectée dans `index_job_files` en **batch**
(une seule requête `executemany` ou `INSERT ... SELECT unnest(...)`). Si la liste est vide,
ne rien insérer.

Le batch d'insertion et l'`UPDATE index_jobs ... status='done'` doivent rester cohérents :
insérer les fichiers avant ou après le mark-done, dans la même séquence. (Pas de transaction
distribuée nécessaire ; en cas d'échec d'insertion des fichiers, le job reste marqué done — les
fichiers sont un détail d'affichage, pas une donnée critique. Logguer un warning si l'insert échoue.)

### 3. API — `backend/src/rag/api/admin.py` + `backend/src/rag/services/jobs.py`

Nouvel endpoint :
```
GET /workspaces/{name}/jobs/{job_id}/files
```
- Service `list_job_files(config_pool, *, workspace_name, job_id, limit=1000) -> dict` :
  - Vérifie que le job appartient au workspace (jointure `index_jobs` ⋈ `workspaces`), sinon `JobNotFound`.
  - `SELECT path, change_type FROM index_job_files WHERE job_id=$1 ORDER BY change_type, path LIMIT $2`.
  - `SELECT count(*)` pour le total.
  - Retourne `{ "files": [{path, change_type}], "total": int, "limit": int }`.
- DTO Pydantic `JobFileEntry { path: str, change_type: Literal["added","modified","deleted"] }`
  et `JobFilesResponse { files: list[JobFileEntry], total: int, limit: int }` dans `schemas/admin.py`.
- Endpoint dans le router admin (même pattern que les autres endpoints jobs).

### 4. Frontend

- **Types** (`workspaces.types.ts`) : `JobFileEntry { path: string; change_type: "added"|"modified"|"deleted" }`,
  `JobFilesResponse { files: JobFileEntry[]; total: number; limit: number }`.
- **API client** (`lib/workspaces.ts`) : `listJobFiles(name, jobId): Promise<JobFilesResponse>`.
- **Hook** (`hooks/useWorkspaces.ts`) : `useWorkspaceJobFiles(name, jobId, enabled)` —
  React Query, `queryKey: ["workspace", name, "jobs", jobId, "files"]`, `enabled` quand la ligne
  est ouverte (lazy).
- **`WorkspaceJobsTab.tsx`** :
  - Rendre **tous** les jobs expandables (retirer `disabled={!hasError}` ; chevron pour tous).
  - Au clic → `toggle(id)`. Quand ouvert, monter un sous-composant `JobDetailPanel` qui appelle
    `useWorkspaceJobFiles` (enabled=isOpen).
  - **`JobDetailPanel`** (nouveau composant, fichier séparé) : affiche métadonnées (source si dispo,
    début/fin formatés, durée), puis :
    - si erreur → `error_message` (bloc rouge, comme aujourd'hui) ;
    - liste des fichiers avec badge type (`+` ajouté vert, `~` modifié ambre, `−` supprimé rouge) ;
    - si `total > limit` → ligne « + N fichiers supplémentaires » ;
    - si `files.length === 0` et pas d'erreur → « aucun détail de fichier (job antérieur) ».
- **i18n** fr/en : clés `jobs.detail.source`, `jobs.detail.started`, `jobs.detail.finished`,
  `jobs.detail.files`, `jobs.detail.added`, `jobs.detail.modified`, `jobs.detail.deleted`,
  `jobs.detail.more`, `jobs.detail.no_files`.

## Gestion d'erreur

| Cas | Comportement |
|---|---|
| Job en erreur | Panneau métadonnées + `error_message` (inchangé) |
| Job réussi avec fichiers | Métadonnées + liste fichiers |
| Job ancien (aucun fichier en base) | Métadonnées + « aucun détail de fichier » |
| 1er sync volumineux (> limite) | 1000 fichiers affichés + « N supplémentaires » |
| Échec insertion fichiers dans l'executor | Job marqué `done` quand même + `log.warning` (détail non critique) |
| Chargement endpoint échoue (frontend) | Message d'erreur dans le panneau, pas de crash |

## Tests (TDD)

**Backend**
- Migration 017 : test d'application (table + index créés) — pattern `tests/integration/test_migration_*`.
- Executor (intégration) : un sync avec 1 added + 1 modified + 1 deleted persiste 3 lignes
  `index_job_files` avec les bons `change_type` ; un fichier skippé (hash inchangé) n'apparaît pas.
- Service `list_job_files` (intégration) : retourne les fichiers d'un job ; `JobNotFound` si job
  d'un autre workspace ; respect de `limit` + `total`.
- DTO `JobFileEntry`/`JobFilesResponse` (unit) : validation `change_type`.

**Frontend (Vitest)**
- `JobDetailPanel` : rend la liste des fichiers (mock du hook) ; affiche « aucun détail » si vide ;
  affiche « N supplémentaires » si `total > limit` ; affiche `error_message` si erreur.
- `WorkspaceJobsTab` : un job `done` est désormais cliquable (chevron présent, pas `disabled`).
  ⚠️ Stabiliser les mocks renvoyant des objets (cf. piège OOM connu : références stables via
  `vi.hoisted`).

## Hors scope

- Backfill rétroactif des jobs existants (impossible — chemins non conservés).
- Pagination « charger plus » au-delà de la limite (1000 suffit pour l'affichage ; YAGNI).
- Persistance / affichage des fichiers **ignorés**.
