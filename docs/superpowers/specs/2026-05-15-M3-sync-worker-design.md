# M3 — Sync Worker + Scheduling git · Design

> **Statut** : design validé, prêt pour rédaction du plan d'implémentation TDD.
> **Précédent** : M2 (API administration) — tag `m2-done`.
> **Suivant après M3** : M4 (indexer engine effectif : providers OpenAI/Voyage/Ollama + chunking + upsert pgvector + API push synchrone + MCP search).

## Objectif

Livrer le **sync worker** qui exécute effectivement les `index_jobs(status='pending')` créés par M2 (manuellement via `POST /reindex` ou par l'utilisateur). Le worker tourne dans le même process FastAPI (asyncio task dans le lifespan), surveille les sources git via polling, déclenche des jobs au timing voulu, et applique le pipeline complet : clone/pull → diff → déduplication SHA-256 → délégation à un `IndexerProtocol`.

À la fin de M3 :
- Les jobs `pending` transitent en `running` puis `done` (ou `error`) automatiquement, sans intervention.
- Une source git ajoutée déclenche un premier sync immédiat.
- Les sources sont re-synchronisées toutes les `sync_interval_seconds` (5 min par défaut).
- Les compteurs `files_changed` / `files_skipped` reflètent la déduplication SHA-256.
- Les jobs `running` orphelins (crash worker) sont automatiquement marqués `error` au boot suivant.
- L'indexation effective (chunks + embeddings + pgvector) est laissée à un `IndexerProtocol` injectable, stubbé en M3 par un `NoOpIndexer` qui maintient seulement `indexed_documents` (hash + timestamp). M4 remplacera ce stub par les vrais providers.

## Scope assumé

| Inclus M3 | Hors M3 |
|---|---|
| `SyncWorker` (asyncio task, lifespan-managed) | Indexer engine effectif (chunking + embeddings + pgvector) — M4 |
| Scheduler : `next_sync_at` → jobs `triggered_by='schedule'` | API push synchrone `POST /workspaces/{name}/index` — M4 |
| Executor : `pending → running → done|error` | API MCP search `POST /mcp` — M4 |
| `git_ops` : clone, pull, diff via subprocess `git` CLI | Multi-worker concurrent + advisory locks — M3+ |
| Storage volume `rag_repos` (`/var/lib/rag/repos/<ws>/<src>/`) | Webhooks GitHub/Azure DevOps — M5+ |
| Déduplication SHA-256 via `indexed_documents` | Backoff exponentiel / circuit breaker — M3+ |
| Recovery au boot : `running` orphelins → `error` | Limite de taille repo (>500MB) — selon besoin |
| Filtres `include` / `exclude` glob | Reranking, chunking sémantique — M4+ |
| Modif rétro M2 : `add_source` set `next_sync_at = now()` | |
| Aucune nouvelle migration DB (utilise champs M1/M2 existants) | |

---

## Décisions arbitrées (brainstorming 2026-05-15)

| Décision | Choix |
|---|---|
| Scope M3 vs M4 | Worker + scheduling + git ops ; indexer M3 = `NoOpIndexer` stub |
| Architecture worker | Single asyncio task dans lifespan, 3 phases (scheduler / picker / executor) |
| Git tooling | `subprocess` `git` CLI (binaire installé dans Dockerfile backend) |
| Storage repos | Volume Docker named `rag_repos` monté `/var/lib/rag/repos/<ws_id>/<src_id>/` |
| Auth git | URL HTTPS avec token PAT depuis Harpocrate, résolu lazy avant clone/pull |
| Résilience | Erreur = retry au prochain cycle ; jobs `running` stale au boot → marqués `error` |
| Scheduling 1er sync | `services/sources.add_source` set `next_sync_at = now()` (modif rétro M2) |
| Concurrence | Single worker, scheduler skip les sources avec job `pending`/`running` ouvert |
| Migration DB | Aucune — utilise champs M1/M2 existants |
| Frontière vers M4 | `IndexerProtocol` à 2 méthodes (`index_file` / `delete_file`) |

---

## Architecture

### Composants

```
backend/src/rag/
├── sync/
│   ├── worker.py            # SyncWorker class : asyncio task, lifespan-managed
│   ├── scheduler.py         # schedule_due_sources(config_pool)
│   ├── executor.py          # execute_next_pending_job(...)
│   ├── git_ops.py           # clone/pull/diff via subprocess + sanitization stderr
│   ├── repo_storage.py      # path resolution /var/lib/rag/repos/<ws>/<src>/
│   └── recovery.py          # reset_stale_running_jobs(config_pool)
├── indexer/
│   ├── protocol.py          # IndexerProtocol
│   └── noop.py              # NoOpIndexer (M3 : maintient indexed_documents seulement)
├── schemas/
│   └── sync.py              # DTOs internes (DueSource, JobToProcess, ChangeSet, GitDiffResult)
├── services/
│   └── sources.py           # MODIFY : add_source set next_sync_at = now()
└── main.py                  # MODIFY : recovery + start SyncWorker + clean shutdown
```

### Frontières

```
main.py (lifespan)
    ├─ await recovery.reset_stale_running_jobs(config_pool)
    └─ SyncWorker(config_pool, admin_dsn, indexer, resolver, settings).start()
          └─ background asyncio task
                └─ boucle infinie :
                     ├─ await scheduler.schedule_due_sources(config_pool, settings)
                     ├─ await executor.execute_next_pending_job(
                     │       config_pool, admin_dsn, indexer, resolver, settings
                     │   )
                     └─ await asyncio.sleep(settings.sync_worker_poll_interval_seconds)
```

L'executor consomme un seul job par cycle (le plus ancien `pending`). Si plusieurs jobs sont en attente, ils seront traités sur les cycles suivants (1 par 30s). Suffisant pour M3 (<20 workspaces, faible débit).

### Settings ajoutés (`config.py`)

```python
sync_worker_poll_interval_seconds: int = 30   # déjà dans .env.example M1
sync_default_interval_seconds: int = 300      # NEW — défaut entre 2 syncs d'une même source
sync_repos_root: Path = Path("/var/lib/rag/repos")   # NEW — racine des clones git
```

### Volume Docker (`docker-compose-dev.yml`)

```yaml
services:
  backend:
    volumes:
      - rag_repos:/var/lib/rag/repos
    # ... reste inchangé

volumes:
  postgres_data:
  caddy_data:
  caddy_config:
  rag_repos:    # NEW — clones git persistants entre runs
```

Le `--reset` de `dev-deploy.sh` purge `rag_repos` via `down -v` (cohérent).

### Frontière vers l'indexer engine (M4)

```python
class IndexerProtocol(Protocol):
    async def index_file(
        self, *,
        workspace_id: UUID,
        path: str,
        content: str,
        content_hash: str,
        indexer_used: str,    # ex: "openai/text-embedding-3-small"
    ) -> int:
        """Index un fichier (chunks + embeddings + upsert pgvector +
        UPDATE indexed_documents). Retourne le nombre de chunks créés.
        """

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        """Supprime tous les chunks pgvector d'un fichier + DELETE
        indexed_documents.
        """
```

**`NoOpIndexer` (M3)** :
- `index_file` :
  - INSERT/UPDATE `indexed_documents (workspace_id, path, content_hash, indexer_used, indexed_at=now())` avec `ON CONFLICT (workspace_id, path) DO UPDATE`
  - retourne `1` (1 chunk fictif)
  - **NE TOUCHE PAS** à la base pgvector workspace
- `delete_file` :
  - DELETE FROM `indexed_documents` WHERE workspace_id AND path

Décision d'injection : `IndexerProtocol` instance est créée au lifespan (`NoOpIndexer(config_pool)` en M3) et passée à `SyncWorker.__init__`. En M4, on remplacera par `RealIndexer(config_pool, workspace_pool_registry, secret_resolver, ...)` sans toucher au code du worker.

---

## Flow A — Scheduler (toutes les 30s)

```sql
-- 1. Identifie les sources dues qui n'ont PAS déjà un job ouvert.
SELECT s.id, s.workspace_id, s.config
FROM workspace_sources s
WHERE s.next_sync_at IS NOT NULL
  AND s.next_sync_at <= now()
  AND NOT EXISTS (
      SELECT 1 FROM index_jobs j
      WHERE j.source_id = s.id
        AND j.status IN ('pending', 'running')
  )
LIMIT 100;

-- 2. Pour chaque due : crée le job + bump next_sync_at (TRANSACTION)
INSERT INTO index_jobs (workspace_id, source_id, triggered_by, status)
VALUES ($1, $2, 'schedule', 'pending');

UPDATE workspace_sources
SET next_sync_at = now() + (extract_sync_interval(config) || ' seconds')::interval
WHERE id = $2;
```

`extract_sync_interval(config)` (Python) :
```python
interval = config.get("sync_interval_seconds", settings.sync_default_interval_seconds)
```

Le `NOT EXISTS` évite la duplication de jobs si un sync précédent traîne (`pending` à cause d'un retard d'exécution, ou `running` en cours).

## Flow B — Picker + Executor

```sql
-- 1. Picke le plus ancien pending et le transitionne en running (atomique).
UPDATE index_jobs
SET status = 'running', started_at = now()
WHERE id = (
    SELECT id FROM index_jobs
    WHERE status = 'pending'
    ORDER BY id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, workspace_id, source_id, triggered_by;
```

`FOR UPDATE SKIP LOCKED` est défensif (anticipation multi-worker M3+), inoffensif en single-worker.

Si la requête ne retourne aucune ligne → aucun job pending, retour immédiat.

**Pipeline du job** (pseudo-code) :

```
1. Charge le contexte (1 SELECT JOIN) :
   - workspace.rag_base, workspace.name
   - indexer_config.provider, indexer_config.model
   - workspace_sources.config (url, branch, auth_ref, include, exclude, last_commit, sync_interval_seconds)

2. Résout auth_ref si présent :
   token = resolver.resolve_with_retry("${vault://rag:" + auth_ref + "}")
   (en cas d'échec → job error, finished_at=now(), error_message)

3. Détermine le path local :
   path = sync_repos_root / workspace_id / source_id

4. Clone ou pull :
   if path/.git n'existe pas :
       git_ops.clone(path, url, branch, token)
       result = GitOpResult(was_fresh_clone=True, current_commit=git rev-parse HEAD)
   else :
       git_ops.pull(path, branch)
       result = GitOpResult(was_fresh_clone=False, current_commit=git rev-parse HEAD)

5. Calcule le diff :
   last_commit = config.get("last_commit")  # peut être None au 1er sync
   if last_commit is None or result.was_fresh_clone :
       changes = git_ops.list_all_files(path)   # tous les fichiers du worktree
   else :
       changes = git_ops.diff_changes(path, last_commit, result.current_commit)

6. Applique les filtres :
   changes = filter_glob(changes, include=config.get("include", ["**/*"]),
                                  exclude=config.get("exclude", []))

7. Traite les fichiers :
   files_changed = 0
   files_skipped = 0
   for f in changes.added + changes.modified :
       try :
           content = (path / f).read_text(encoding="utf-8")
       except UnicodeDecodeError :
           continue  # binaire skippé silencieusement, ne compte pas

       content_hash = "sha256:" + sha256(content.encode()).hexdigest()
       indexer_used = f"{provider}/{model}"

       existing = SELECT content_hash FROM indexed_documents
                  WHERE workspace_id=$1 AND path=$2
       if existing == content_hash :
           files_skipped += 1
           continue

       await indexer.index_file(
           workspace_id=workspace_id, path=f, content=content,
           content_hash=content_hash, indexer_used=indexer_used,
       )
       files_changed += 1

   for f in changes.deleted :
       await indexer.delete_file(workspace_id=workspace_id, path=f)
       files_changed += 1

8. UPDATE workspace_sources :
   SET config = jsonb_set(config, '{last_commit}', to_jsonb($1::text)),
       last_indexed_at = now()
   WHERE id = $2

9. UPDATE index_jobs :
   SET status = 'done',
       finished_at = now(),
       duration_ms = (now() - started_at) * 1000,
       files_changed = $1,
       files_skipped = $2
   WHERE id = $3
```

Toute exception entre 2-9 → bloc `except` :
```sql
UPDATE index_jobs SET status='error', error_message=<msg sanitized>,
                      finished_at=now(),
                      duration_ms=(now() - started_at) * 1000
WHERE id=$1
```
`last_commit` n'est PAS avancé en cas d'erreur → retry naturel au prochain cycle.

## Flow C — Recovery au boot

Avant de démarrer la task du worker, le lifespan exécute :

```sql
UPDATE index_jobs
SET status='error',
    error_message='stale_at_boot',
    finished_at=now(),
    duration_ms=CASE
        WHEN started_at IS NOT NULL THEN
            EXTRACT(MILLISECONDS FROM (now() - started_at))::int
        ELSE 0
    END
WHERE status='running';
```

Garantit qu'aucun job ne reste bloqué en `running` après un crash. Les sources concernées ont leur `next_sync_at` intact → seront re-traitées au prochain cycle de scheduling.

---

## Mapping exceptions → status job

Le worker n'expose pas d'endpoints HTTP, donc pas de `AdminError` HTTPS-mappés. Les exceptions sont capturées et écrites dans `error_message` (max 500 chars, tronqué si plus long) :

| Cause | `error_message` |
|---|---|
| `git_ops.GitCloneError` | `"git clone failed: <stderr sanitized>"` |
| `git_ops.GitPullError` | `"git pull failed: <stderr sanitized>"` |
| `secrets.VaultLookupFailed` | `"auth_ref not resolvable: <ref>"` |
| `secrets.VaultUnreachable` | `"vault unreachable"` |
| `UnicodeDecodeError` sur 1 fichier | skip silencieux (le fichier, pas le job — pas compté) |
| Toute autre `Exception` | `f"unexpected: {type(e).__name__}: <str(e) sanitized 200 chars>"` + `log.exception` côté logs |

**Sanitization stderr git** : avant écriture en base, regex `r"https://[^@\s]+@"` → `"https://***@"` pour purger l'URL token-inline.

## Modification rétro M2

Dans `services/sources.add_source` (M2), à l'INSERT :

```python
# Trigger le premier sync immédiatement au prochain cycle du worker.
await conn.execute(
    """
    INSERT INTO workspace_sources (workspace_id, type, config, next_sync_at)
    VALUES ($1, $2, $3::jsonb, now())
    RETURNING id, type, config, last_indexed_at, created_at
    """,
    ...
)
```

Tests M2 inchangés (les fixtures n'asserent pas `next_sync_at`). Test additionnel M3 confirmant `next_sync_at IS NOT NULL` à la création.

---

## Test plan

~35 nouveaux tests. Coverage cible : ≥95% sur `sync/`, `indexer/noop.py`.

### Unit (~15)

- `repo_storage` : path resolution (workspace_id et source_id UUID stricts), mkdir, refus de paths contenant `..` ou `/`
- `noop_indexer` :
  - `index_file` : INSERT si path absent, UPDATE si présent (ON CONFLICT), retourne 1
  - `delete_file` : DELETE OK, idempotent si absent
- `recovery.reset_stale_running_jobs` : UPDATE `running` → `error` avec message `stale_at_boot`
- `scheduler.schedule_due_sources` :
  - Sources `next_sync_at <= now()` créent des jobs
  - Sources `next_sync_at > now()` ne créent rien
  - Sources avec job `pending`/`running` ouvert sont skippées
  - `next_sync_at` bump après création
- `executor` (sanitize_stderr, filter_glob, _truncate_error)

### Intégration (~15) avec fixtures git éphémères

Fixture `git_repo(tmp_path)` :
```python
@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", repo], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", repo, work], check=True)
    # commits scénarisés via tests
    return repo
```

- `git_ops.clone` : repo local → path/.git existe
- `git_ops.pull` : commit nouveau → file récupéré
- `git_ops.diff_changes` : add/modify/delete détectés
- `git_ops.list_all_files` : 1er sync, tous fichiers du worktree
- `executor.process_job` E2E avec `NoOpIndexer` :
  - 1er sync : tous fichiers indexés, `files_changed = N`, `files_skipped = 0`, `last_commit` posé
  - 2e sync sans changement : `files_changed = 0`, `files_skipped = N` (dédup)
  - 2e sync avec 1 modif + 1 ajout : `files_changed = 2`, `files_skipped = N-1`
  - 2e sync avec 1 suppression : `files_changed = 1`, `delete_file` appelé
- Erreurs : repo inexistant → `error_message = "git clone failed:..."`, token vault failed → `error_message = "auth_ref not resolvable"`

### API E2E (~5)

- `SyncWorker` start/stop propre au lifespan (`TestClient(app)` puis vérifier que la task a tourné au moins un cycle)
- `POST /workspaces/{name}/reindex` → polling worker → status final `done`
- `add_source` avec next_sync_at=now() → après 1 cycle worker → un job `triggered_by='schedule'` existe
- Recovery au boot : insère manuellement un job `running` orphelin, redémarre l'app, vérifie qu'il est marqué `error` `stale_at_boot`

---

## Risques identifiés

1. **Repos énormes en HTTPS** — clone d'un repo >1GB peut consommer beaucoup de temps + bande passante. **Mitigation M3** : aucune. Clone complet nécessaire car `git diff <last_commit>..HEAD` exige que `last_commit` soit dans l'historique local — incompatible avec `--depth=1`. Pour les gros repos, alternative future : shallow clone + fallback "list all files" si `last_commit` introuvable. À implémenter si on observe le besoin.

2. **Token leakage via stderr** — git peut écho l'URL avec token sur stderr. **Mitigation** : `GIT_TERMINAL_PROMPT=0` env var pour git ; regex de sanitization `https://[^@]+@` → `https://***@` sur tout output avant log/persistance.

3. **Token leakage via `.git/config`** — git stocke l'URL avec token dans `.git/config` côté disque. Le volume `rag_repos` n'est pas exposé publiquement mais reste lisible par un opérateur. **Mitigation M3** : acceptable (volume protégé). Durcissement plus tard via `GIT_ASKPASS` (token jamais persistant dans .git/config).

4. **Race scheduler vs executor** — un job pending créé par le scheduler peut être pické au même cycle par l'executor. Pas un bug fonctionnel (c'est le but) mais à noter. La sub-query `NOT EXISTS pending|running` du scheduler empêche les doublons.

5. **Concurrent worker boot** — `scale=1` enforced côté compose. Multi-worker = M3+ avec advisory locks.

6. **`/var/lib/rag/repos` saturé** — volume Docker qui grossit indéfiniment. **Mitigation M3** : pas de cleanup auto, monitoring manuel (`du -sh`). Purge : `docker compose down -v && docker volume rm rag_repos`.

7. **`UnicodeDecodeError` silencieux** — un PR qui ajoute des binaires (`.png`, `.zip`) ne fera pas planter le sync mais ne sera pas indexé. Comportement attendu. Pas de compteur dédié en M3 ; à ajouter si demandé (`files_binary_skipped`).

8. **Sync interval invariant** — `sync_default_interval_seconds=300` (5 min). Si l'utilisateur configure `sync_interval_seconds=10` (très court), le worker tournera tout le temps. **Mitigation M3** : aucune. À traiter via guardrails si abusif (`MIN_SYNC_INTERVAL = 60`).

9. **Indexer M3 = NoOp** — tant que M4 n'arrive pas, aucun chunk n'est créé en pgvector. Les bases workspace `rag_<name>` restent vides. C'est **par design** : M3 valide le pipeline, M4 branche le moteur.

---

## Conformité CLAUDE.md

- Python 3.12, async/await, asyncpg direct (pas SQLAlchemy) ✓
- Pydantic v2 pour les DTOs (`schemas/sync.py`) ✓
- structlog (jamais `print`) ; tokens git jamais logués en clair ✓
- Fichiers ≤300 lignes ; services SRP ; méthodes 5-15 lignes ✓
- Pas de quick-and-dirty : sanitization stderr explicite, recovery au boot, idempotence, retry naturel sans backoff implicite ✓
- Tests intégration sur Postgres LXC partagé (continuité M2) ✓
- Frontière vers M4 nette via `IndexerProtocol` ✓
