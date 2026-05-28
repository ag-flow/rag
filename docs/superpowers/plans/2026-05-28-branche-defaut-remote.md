# Détection de la branche par défaut du remote — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quand l'utilisateur ne précise pas de branche pour une source git, détecter la branche par défaut réelle du dépôt distant au lieu de forcer `main`.

**Architecture:** Une fonction de détection sans effet de bord (`git ls-remote --symref … HEAD`) dans la couche `git_ops`. Un helper de résolution dans le service `sources` qui, branche vide, détecte et stocke la branche concrète à l'écriture — ou retombe sur `main` avec un avertissement non bloquant remonté à l'IHM. Le frontend rend le champ branche optionnel et affiche un toast en cas de repli.

**Tech Stack:** Python 3.12 + asyncpg + structlog + pytest (backend) ; React 18 + TS strict + zod + react-hook-form + TanStack Query + Vitest (frontend). Spec : `docs/superpowers/specs/2026-05-28-branche-defaut-remote-design.md`.

**Branche de travail :** `dev` (toujours — cf. CLAUDE.md).

**Référence d'implémentation déjà en place (ne pas réécrire) :**
- `backend/src/rag/sync/git_ops.py` : `_build_authenticated_url(url, token)`, `sanitize_git_output(text)`, `clone`, `pull`.
- `backend/src/rag/services/sources.py` : `add_source`, `update_source`, `test_source_connection`, `_source_to_dict`, `_ResolverProtocol`, `is_vault_ref` (importé).
- `backend/src/rag/api/admin.py` : `post_source` (l.190), `patch_source` (l.204) ; `request.app.state.resolver` disponible.
- `frontend/src/pages/workspace/AddSourceDialog.tsx`, `frontend/src/lib/workspaces.types.ts`, `frontend/src/i18n/{fr,en}/workspace.json`.

---

## Task 1 : Parsing de la sortie `--symref` (fonction pure)

**Files:**
- Modify: `backend/src/rag/sync/git_ops.py`
- Test: `backend/tests/unit/test_git_ops_parse.py` (create)

- [ ] **Step 1 : Écrire le test qui échoue**

Create `backend/tests/unit/test_git_ops_parse.py` :

```python
from __future__ import annotations

from rag.sync.git_ops import _parse_symref_head


def test_parse_symref_head_extracts_main() -> None:
    out = "ref: refs/heads/main\tHEAD\n0123abcdef\tHEAD\n"
    assert _parse_symref_head(out) == "main"


def test_parse_symref_head_extracts_master() -> None:
    out = "ref: refs/heads/master\tHEAD\nabc123\tHEAD\n"
    assert _parse_symref_head(out) == "master"


def test_parse_symref_head_extracts_branch_with_slash() -> None:
    out = "ref: refs/heads/feature/x\tHEAD\nabc\tHEAD\n"
    assert _parse_symref_head(out) == "feature/x"


def test_parse_symref_head_none_when_no_symref() -> None:
    assert _parse_symref_head("0123abc\tHEAD\n") is None


def test_parse_symref_head_none_when_empty() -> None:
    assert _parse_symref_head("") is None
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run: `cd backend && uv run pytest tests/unit/test_git_ops_parse.py -v`
Expected: FAIL — `ImportError: cannot import name '_parse_symref_head'`.

- [ ] **Step 3 : Implémenter le parsing**

Dans `backend/src/rag/sync/git_ops.py`, après la constante `_TOKEN_URL_RE` (l.25) et `sanitize_git_output`, ajouter :

```python
# Ligne symref de `git ls-remote --symref <url> HEAD` :
#   "ref: refs/heads/<branch>\tHEAD"
_SYMREF_HEAD_RE = re.compile(r"^ref:\s+refs/heads/(?P<branch>\S+)\s+HEAD", re.MULTILINE)


def _parse_symref_head(stdout: str) -> str | None:
    """Extrait le nom de branche de la ligne symref de `ls-remote --symref HEAD`.

    Retourne None si aucune ligne symref n'est présente.
    """
    match = _SYMREF_HEAD_RE.search(stdout)
    return match.group("branch") if match else None
```

(`re` est déjà importé en tête de fichier.)

- [ ] **Step 4 : Lancer le test, vérifier le succès**

Run: `cd backend && uv run pytest tests/unit/test_git_ops_parse.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5 : Commit**

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/unit/test_git_ops_parse.py
git commit -m "feat(sync): parsing symref HEAD pour branche par défaut"
```

---

## Task 2 : `detect_default_branch` (integration git locale)

**Files:**
- Modify: `backend/tests/integration/_git_fixture.py` (param `default_branch`)
- Modify: `backend/src/rag/sync/git_ops.py`
- Test: `backend/tests/integration/test_git_ops_branch.py` (create)

- [ ] **Step 1 : Étendre la fixture pour supporter une branche par défaut custom**

Dans `backend/tests/integration/_git_fixture.py`, remplacer la signature et les deux usages de `"main"` :

```python
def make_bare_repo_with_commits(
    tmp_path: Path, files: dict[str, str], default_branch: str = "main"
) -> Path:
    """Crée un repo bare avec des commits initialisés depuis un dict
    {path: content}. Retourne le path du repo bare (à utiliser comme URL
    de clone : `file:///tmp/.../bare.git`).

    `default_branch` fixe la branche initiale du bare (HEAD symref).
    """
    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "init", "--bare", f"--initial-branch={default_branch}", str(bare)],
        check=True,
        capture_output=True,
    )

    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", str(bare), str(work)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "config", "user.email", "test@test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "config", "user.name", "test"],
        check=True,
    )

    for path, content in files.items():
        full = work / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

    subprocess.run(["git", "-C", str(work), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "push", "origin", default_branch],
        check=True,
        capture_output=True,
    )
    return bare
```

(Le défaut `"main"` garde les appels existants inchangés.)

- [ ] **Step 2 : Écrire le test qui échoue**

Create `backend/tests/integration/test_git_ops_branch.py` :

```python
from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import detect_default_branch
from tests.integration._git_fixture import make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_detect_default_branch_main(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="main")
    assert await detect_default_branch(url=f"file://{bare}", token=None) == "main"


@pytest.mark.asyncio
async def test_detect_default_branch_master(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="master")
    assert await detect_default_branch(url=f"file://{bare}", token=None) == "master"


@pytest.mark.asyncio
async def test_detect_default_branch_none_when_unreachable(tmp_path: Path) -> None:
    result = await detect_default_branch(
        url="https://example.invalid/x/y.git", token=None, timeout=5.0
    )
    assert result is None
```

- [ ] **Step 3 : Lancer le test, vérifier l'échec**

Run: `cd backend && uv run pytest tests/integration/test_git_ops_branch.py -v`
Expected: FAIL — `ImportError: cannot import name 'detect_default_branch'`.

- [ ] **Step 4 : Implémenter `detect_default_branch`**

Dans `backend/src/rag/sync/git_ops.py`, après `pull` (l.143), ajouter :

```python
async def detect_default_branch(
    *, url: str, token: str | None, timeout: float = 15.0
) -> str | None:
    """Branche par défaut du remote via `git ls-remote --symref <url> HEAD`.

    Retourne le nom de branche (ex: "main", "master"), ou None si
    indéterminable (échec réseau, timeout, repo injoignable, pas de symref).
    Ne lève jamais : le repli est de la responsabilité de l'appelant.
    """
    auth_url = _build_authenticated_url(url, token)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            "--symref",
            auth_url,
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, FileNotFoundError, NotADirectoryError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return _parse_symref_head(stdout_b.decode("utf-8", errors="replace"))
```

(`asyncio`, `os` sont déjà importés en tête de fichier.)

- [ ] **Step 5 : Lancer les tests, vérifier le succès + non-régression de la fixture**

Run: `cd backend && uv run pytest tests/integration/test_git_ops_branch.py tests/integration/test_git_ops_clone.py tests/integration/test_git_ops_pull.py -v`
Expected: PASS — les 3 nouveaux tests + les tests clone/pull existants (la fixture reste rétrocompatible).

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/integration/_git_fixture.py backend/tests/integration/test_git_ops_branch.py
git commit -m "feat(sync): detect_default_branch via git ls-remote --symref"
```

---

## Task 3 : Helper `_resolve_branch_for_write` (unit)

**Files:**
- Modify: `backend/src/rag/services/sources.py`
- Test: `backend/tests/unit/services/test_branch_resolution.py` (create)

- [ ] **Step 1 : Écrire le test qui échoue**

Create `backend/tests/unit/services/test_branch_resolution.py` :

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rag.services.sources import _resolve_branch_for_write


@pytest.mark.asyncio
async def test_keeps_explicit_branch_without_detection() -> None:
    config = {"url": "https://github.com/x/y", "branch": "develop"}
    with patch("rag.services.sources.detect_default_branch", AsyncMock()) as detect:
        out, warning = await _resolve_branch_for_write(config, token=None)
    assert out["branch"] == "develop"
    assert warning is None
    detect.assert_not_called()


@pytest.mark.asyncio
async def test_detects_when_branch_empty() -> None:
    config = {"url": "https://github.com/x/y", "branch": ""}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value="master")
    ):
        out, warning = await _resolve_branch_for_write(config, token="tok")
    assert out["branch"] == "master"
    assert warning is None


@pytest.mark.asyncio
async def test_detects_when_branch_absent() -> None:
    config = {"url": "https://github.com/x/y"}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value="main")
    ):
        out, warning = await _resolve_branch_for_write(config, token=None)
    assert out["branch"] == "main"
    assert warning is None


@pytest.mark.asyncio
async def test_fallback_main_with_warning_on_detection_failure() -> None:
    config = {"url": "https://github.com/x/y", "branch": ""}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value=None)
    ):
        out, warning = await _resolve_branch_for_write(config, token=None)
    assert out["branch"] == "main"
    assert warning is not None
    assert "main" in warning


@pytest.mark.asyncio
async def test_does_not_mutate_input_config() -> None:
    config = {"url": "https://github.com/x/y"}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value="master")
    ):
        await _resolve_branch_for_write(config, token=None)
    assert "branch" not in config  # l'original n'est pas modifié
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run: `cd backend && uv run pytest tests/unit/services/test_branch_resolution.py -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_branch_for_write'`.

- [ ] **Step 3 : Implémenter le helper**

Dans `backend/src/rag/services/sources.py` :

a) Ajouter l'import en tête (après les imports `rag.*` existants, l.13-22) :

```python
from rag.sync.git_ops import detect_default_branch
```

b) Après `_get_workspace_id_or_raise` (l.35), ajouter :

```python
async def _resolve_branch_for_write(
    config: dict[str, Any], *, token: str | None
) -> tuple[dict[str, Any], str | None]:
    """Garantit une branche concrète dans `config`.

    - Branche déjà fournie (non vide) → inchangée, pas d'avertissement.
    - Branche vide/absente → détecte la branche par défaut du remote.
      Détection OK → branche détectée. Échec → repli "main" + avertissement.

    Retourne (config copié avec branche résolue, message d'avertissement | None).
    Ne mute pas le dict d'entrée.
    """
    config = dict(config)
    if config.get("branch"):
        return config, None
    detected = await detect_default_branch(url=config.get("url", ""), token=token)
    if detected:
        config["branch"] = detected
        return config, None
    config["branch"] = "main"
    log.warning("source.branch_detect_failed", url=config.get("url", ""))
    return config, "Branche par défaut non détectée, repli sur 'main'."
```

- [ ] **Step 4 : Lancer le test, vérifier le succès**

Run: `cd backend && uv run pytest tests/unit/services/test_branch_resolution.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5 : Commit**

```bash
git add backend/src/rag/services/sources.py backend/tests/unit/services/test_branch_resolution.py
git commit -m "feat(sources): helper _resolve_branch_for_write"
```

---

## Task 4 : Schéma `branch_warning` + intégration dans `add_source`

**Files:**
- Modify: `backend/src/rag/schemas/admin.py:135-141` (`SourceResponse`)
- Modify: `backend/src/rag/services/sources.py` (`add_source`)
- Test: `backend/tests/integration/test_services_sources.py` (ajout)

- [ ] **Step 1 : Ajouter le champ au schéma de réponse**

Dans `backend/src/rag/schemas/admin.py`, classe `SourceResponse` (l.135), ajouter le champ après `created_at` :

```python
class SourceResponse(BaseModel):
    id: UUID
    name: str | None
    type: str
    config: dict[str, Any]
    last_indexed_at: str | None
    created_at: str
    branch_warning: str | None = None
```

- [ ] **Step 2 : Écrire le test d'intégration qui échoue**

Dans `backend/tests/integration/test_services_sources.py`, ajouter en tête l'import de la fixture git (après les imports existants) :

```python
from tests.integration._git_fixture import make_bare_repo_with_commits
```

Puis ajouter ces tests en fin de fichier :

```python
@pytest.mark.asyncio
async def test_add_source_empty_branch_detects_default(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None, tmp_path: Path
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await _setup_ws(pg_container, session_pool, "ws_branch_a")
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="master")
    src = await add_source(
        workspace_name="ws_branch_a",
        request=SourceCreateRequest(
            name="repo1",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={"url": f"file://{bare}", "include": ["**/*.md"], "exclude": []},
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    assert src["config"]["branch"] == "master"
    assert src["branch_warning"] is None


@pytest.mark.asyncio
async def test_add_source_unreachable_falls_back_to_main_with_warning(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await _setup_ws(pg_container, session_pool, "ws_branch_b")
    src = await add_source(
        workspace_name="ws_branch_b",
        request=SourceCreateRequest(
            name="repo2",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={
                "url": "https://example.invalid/x/y.git",
                "include": ["**/*.md"],
                "exclude": [],
            },
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    assert src["config"]["branch"] == "main"
    assert src["branch_warning"] is not None


@pytest.mark.asyncio
async def test_add_source_explicit_branch_no_detection(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await _setup_ws(pg_container, session_pool, "ws_branch_c")
    src = await add_source(
        workspace_name="ws_branch_c",
        request=SourceCreateRequest(
            name="repo3",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={
                "url": "https://example.invalid/x/y.git",
                "branch": "develop",
                "include": [],
                "exclude": [],
            },
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    assert src["config"]["branch"] == "develop"
    assert src["branch_warning"] is None
```

Vérifier que `Path` est importé en tête du fichier (`from pathlib import Path` est déjà présent l.5).

- [ ] **Step 3 : Lancer le test, vérifier l'échec**

Run: `cd backend && uv run pytest tests/integration/test_services_sources.py -k "branch" -v` (Postgres requis — cf. `docs/test.md` / pattern run-test.sh)
Expected: FAIL — `KeyError: 'branch_warning'` (le dict retourné n'a pas encore la clé).

- [ ] **Step 4 : Intégrer la résolution dans `add_source`**

Dans `backend/src/rag/services/sources.py`, fonction `add_source`. Juste avant le bloc `try:` de l'INSERT (l.73), insérer :

```python
    config, branch_warning = await _resolve_branch_for_write(
        config, token=request.auth_value
    )
```

Puis remplacer le `return _source_to_dict(row)` final (l.97) par :

```python
    result = _source_to_dict(row)
    result["branch_warning"] = branch_warning
    return result
```

- [ ] **Step 5 : Lancer les tests, vérifier le succès**

Run: `cd backend && uv run pytest tests/integration/test_services_sources.py -k "branch" -v`
Expected: PASS — 3 passed.

- [ ] **Step 6 : Commit**

```bash
git add backend/src/rag/schemas/admin.py backend/src/rag/services/sources.py backend/tests/integration/test_services_sources.py
git commit -m "feat(sources): détection branche par défaut à la création + branch_warning"
```

---

## Task 5 : Intégration dans `update_source` (résolution token existant)

**Files:**
- Modify: `backend/src/rag/services/sources.py` (`update_source`)
- Test: `backend/tests/integration/test_services_sources.py` (ajout)

- [ ] **Step 1 : Écrire le test d'intégration qui échoue**

Dans `backend/tests/integration/test_services_sources.py`, ajouter en fin de fichier :

```python
@pytest.mark.asyncio
async def test_update_source_empty_branch_redetects(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None, tmp_path: Path
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_branch_upd")
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="master")
    created = await add_source(
        workspace_name="ws_branch_upd",
        request=SourceCreateRequest(
            name="repo-upd",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={"url": f"file://{bare}", "branch": "main", "include": [], "exclude": []},
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    updated = await update_source(
        workspace_name="ws_branch_upd",
        source_id=created["id"],
        request=SourceUpdateRequest(
            auth_value=None,
            config={"url": f"file://{bare}", "include": [], "exclude": []},
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
        resolver=resolver,  # type: ignore[arg-type]
    )
    assert updated["config"]["branch"] == "master"
    assert updated["branch_warning"] is None
```

Ajouter l'import manquant en tête du fichier (à côté de `add_source`) :

```python
from rag.services.sources import add_source, delete_source, list_sources, update_source
```

Et l'import du DTO (la ligne d'import depuis `rag.schemas.admin` doit inclure `SourceUpdateRequest`) :

```python
from rag.schemas.admin import (
    IndexerSpec,
    SourceCreateRequest,
    SourceUpdateRequest,
    WorkspaceCreateRequest,
)
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run: `cd backend && uv run pytest tests/integration/test_services_sources.py::test_update_source_empty_branch_redetects -v`
Expected: FAIL — `TypeError: update_source() got an unexpected keyword argument 'resolver'`.

- [ ] **Step 3 : Ajouter `resolver` à `update_source` et résoudre la branche**

Dans `backend/src/rag/services/sources.py`, fonction `update_source` (l.116), modifier la signature pour ajouter `resolver` :

```python
async def update_source(
    *,
    workspace_name: str,
    source_id: str,
    request: SourceUpdateRequest,
    config_pool: asyncpg.Pool,
    harpocrate_vaults_service: HarpocrateVaultsService,
    resolver: _ResolverProtocol,
) -> dict[str, Any]:
```

Juste avant le bloc `async with config_pool.acquire() as conn:` de l'UPDATE (l.185), insérer :

```python
    detect_token: str | None = request.auth_value
    if not detect_token and existing_ref and is_vault_ref(existing_ref):
        try:
            detect_token = await resolver.resolve_with_retry(existing_ref)
        except Exception:
            detect_token = None
    config, branch_warning = await _resolve_branch_for_write(config, token=detect_token)
```

Puis remplacer le `return _source_to_dict(row)` final (l.199) par :

```python
    result = _source_to_dict(row)
    result["branch_warning"] = branch_warning
    return result
```

- [ ] **Step 4 : Lancer le test, vérifier le succès**

Run: `cd backend && uv run pytest tests/integration/test_services_sources.py::test_update_source_empty_branch_redetects -v`
Expected: PASS — 1 passed.

- [ ] **Step 5 : Commit**

```bash
git add backend/src/rag/services/sources.py backend/tests/integration/test_services_sources.py
git commit -m "feat(sources): redétection branche par défaut à l'édition"
```

---

## Task 6 : Câbler `resolver` dans l'endpoint `patch_source`

**Files:**
- Modify: `backend/src/rag/api/admin.py:204-217` (`patch_source`)
- Test: `backend/tests/api/test_admin_wireup.py` (vérification existante) ou contrôle manuel

- [ ] **Step 1 : Passer le resolver depuis l'app state**

Dans `backend/src/rag/api/admin.py`, fonction `patch_source` (l.210), ajouter l'argument `resolver` à l'appel :

```python
        row = await update_source(
            workspace_name=name,
            source_id=source_id,
            request=payload,
            config_pool=_config_pool(request),
            harpocrate_vaults_service=request.app.state.harpocrate_vaults_service,
            resolver=request.app.state.resolver,
        )
```

(`post_source` reste inchangé : à la création, le token clair `auth_value` suffit, pas besoin de resolver.)

- [ ] **Step 2 : Vérifier que l'app démarre sans erreur d'import / wireup**

Run: `cd backend && uv run pytest tests/api/test_admin_wireup.py -v`
Expected: PASS — le router admin se construit sans erreur.

- [ ] **Step 3 : Vérifier l'absence de régression lint sur les fichiers backend touchés**

Run: `cd backend && uv run ruff check src/rag/sync/git_ops.py src/rag/services/sources.py src/rag/schemas/admin.py src/rag/api/admin.py`
Expected: `All checks passed!`

- [ ] **Step 4 : Commit**

```bash
git add backend/src/rag/api/admin.py
git commit -m "feat(api): passe resolver à update_source pour détection branche"
```

---

## Task 7 : Types frontend

**Files:**
- Modify: `frontend/src/lib/workspaces.types.ts:51-65`

- [ ] **Step 1 : Rendre la branche optionnelle en entrée et ajouter `branch_warning`**

Dans `frontend/src/lib/workspaces.types.ts` :

a) Ajouter `branch_warning` au type `Source` (l.51) :

```typescript
export type Source = {
  id: string;
  name: string | null;
  type: "git";
  config: SourceConfig;
  last_indexed_at: string | null;
  created_at: string;
  branch_warning?: string | null;
};
```

b) Rendre `branch` optionnel dans `SourceConfigInput` (l.60) :

```typescript
type SourceConfigInput = {
  url: string;
  branch?: string;
  include: string[];
  exclude: string[];
};
```

- [ ] **Step 2 : Vérifier la compilation TS stricte**

Run: `cd frontend && npx tsc --noEmit`
Expected: pas d'erreur (les usages existants envoyant `branch` restent valides).

- [ ] **Step 3 : Commit**

```bash
git add frontend/src/lib/workspaces.types.ts
git commit -m "feat(front): branch optionnel + branch_warning dans les types Source"
```

---

## Task 8 : Clés i18n fr/en

**Files:**
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Step 1 : Ajouter les clés fr**

Dans `frontend/src/i18n/fr/workspace.json`, dans `sources.fields` (après `"branch": "Branche",` l.72), ajouter :

```json
      "branch_placeholder": "branche par défaut du dépôt (ex: main)",
```

Dans `sources.add` (après `"success": "Source ajoutée.",` l.84), ajouter :

```json
      "branch_warning": "Branche par défaut non détectée, « main » utilisé. Vérifiez si la synchronisation échoue.",
```

- [ ] **Step 2 : Ajouter les clés en (mêmes chemins)**

Dans `frontend/src/i18n/en/workspace.json`, dans `sources.fields`, ajouter :

```json
      "branch_placeholder": "repository default branch (e.g. main)",
```

Dans `sources.add`, ajouter :

```json
      "branch_warning": "Default branch not detected, fell back to \"main\". Check if sync fails.",
```

- [ ] **Step 3 : Vérifier que les JSON sont valides**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/workspace.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/en/workspace.json','utf8')); console.log('ok')"`
Expected: `ok`

- [ ] **Step 4 : Commit**

```bash
git add frontend/src/i18n/fr/workspace.json frontend/src/i18n/en/workspace.json
git commit -m "feat(i18n): clés branch_placeholder + branch_warning"
```

---

## Task 9 : `AddSourceDialog` — champ optionnel, omission, toast d'avertissement

**Files:**
- Modify: `frontend/src/pages/workspace/AddSourceDialog.tsx`
- Test: `frontend/src/pages/workspace/__tests__/AddSourceDialog.test.tsx` (ajout)

- [ ] **Step 1 : Écrire les tests frontend qui échouent**

Dans `frontend/src/pages/workspace/__tests__/AddSourceDialog.test.tsx` :

a) Remplacer la 1re ligne d'import par (ajout de `beforeEach`) :

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
```

b) Remplacer le bloc complet `const mockMutate = vi.fn();` + les trois `vi.mock(...)` (lignes 6-22 du fichier original) par cette version. Les variables consommées dans une factory `vi.mock` doivent être créées via `vi.hoisted` (sinon erreur « Cannot access before initialization ») :

```typescript
const { mockMutate, mockToast, mockAddResponse } = vi.hoisted(() => ({
  mockMutate: vi.fn(),
  mockToast: vi.fn(),
  mockAddResponse: { value: { id: "s1", branch_warning: null as string | null } },
}));

vi.mock("@/hooks/useWorkspaces", () => ({
  useAddSource: () => ({
    mutate: (payload: unknown, opts?: { onSuccess?: (d: unknown) => void }) => {
      mockMutate(payload);
      opts?.onSuccess?.(mockAddResponse.value);
    },
    isPending: false,
  }),
  useUpdateSource: () => ({ mutate: vi.fn(), isPending: false }),
  useTestSourceConnection: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useHarpocrateVaults", () => ({
  useVaults: () => ({
    data: [{ name: "vault-default", label: "Default Vault", api_key_id: "key-1" }],
  }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: mockToast }),
}));
```

c) Ajouter un `beforeEach` en tête du `describe("AddSourceDialog", …)` pour réinitialiser les mocks entre tests :

```typescript
  beforeEach(() => {
    mockMutate.mockClear();
    mockToast.mockClear();
    mockAddResponse.value = { id: "s1", branch_warning: null };
  });
```

d) Ajouter ces trois tests dans le `describe`. Note : à la soumission, `branch` vaut `undefined` quand le champ est vide — la clé existe dans l'objet JS (elle n'est omise qu'à la sérialisation JSON), donc on assert `toBeUndefined()`, pas l'absence de clé :

```typescript
  it("laisse la branche undefined quand le champ est vide", async () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    fireEvent.change(screen.getByPlaceholderText(/ex\. mon-repo/), {
      target: { value: "my-repo" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://github.com/..."), {
      target: { value: "https://github.com/org/repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ajouter$/i }));
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
    const payload = mockMutate.mock.calls[0][0] as { config: { branch?: string } };
    expect(payload.config.branch).toBeUndefined();
  });

  it("transmet la branche quand elle est saisie", async () => {
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    fireEvent.change(screen.getByPlaceholderText(/ex\. mon-repo/), {
      target: { value: "my-repo" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://github.com/..."), {
      target: { value: "https://github.com/org/repo" },
    });
    fireEvent.change(screen.getByPlaceholderText(/branche par défaut/i), {
      target: { value: "develop" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ajouter$/i }));
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
    const payload = mockMutate.mock.calls[0][0] as { config: { branch?: string } };
    expect(payload.config.branch).toBe("develop");
  });

  it("affiche un toast d'avertissement quand branch_warning est présent", async () => {
    mockAddResponse.value = { id: "s1", branch_warning: "w" };
    renderWithProviders(
      <AddSourceDialog name="my-workspace" open={true} onOpenChange={() => {}} />,
    );
    fireEvent.change(screen.getByPlaceholderText(/ex\. mon-repo/), {
      target: { value: "my-repo" },
    });
    fireEvent.change(screen.getByPlaceholderText("https://github.com/..."), {
      target: { value: "https://github.com/org/repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^ajouter$/i }));
    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
    // deux toasts : avertissement (branch_warning) + succès
    expect(mockToast).toHaveBeenCalledTimes(2);
  });
```

- [ ] **Step 2 : Lancer les tests, vérifier l'échec**

Run: `cd frontend && npm run test:run -- AddSourceDialog`
Expected: FAIL — la branche est encore envoyée (placeholder absent, `branch` toujours présent dans le payload).

- [ ] **Step 3 : Mettre à jour les schémas et defaults**

Dans `frontend/src/pages/workspace/AddSourceDialog.tsx` :

a) `createSchema` (l.27) et `editSchema` (l.37) — remplacer la ligne `branch` par :

```typescript
  branch: z.string().optional(),
```

b) `createForm` defaultValues (l.80) et `editForm` defaultValues (l.90) — `branch: "main"` devient :

```typescript
      branch: "",
```

c) Dans le `useEffect` (l.111-120), bloc `createForm.reset({...})` — `branch: "main"` devient `branch: ""`. Le bloc `editForm.reset` garde `branch: source.config.branch` (inchangé).

- [ ] **Step 4 : Omettre la branche vide à la soumission**

Dans `frontend/src/pages/workspace/AddSourceDialog.tsx`, ajouter ce helper à côté de `splitCsv` (l.56) :

```typescript
const branchOrUndefined = (b: string | undefined): string | undefined => {
  const trimmed = (b ?? "").trim();
  return trimmed === "" ? undefined : trimmed;
};
```

Dans `onSubmitCreate` (l.131-136), remplacer `branch: v.branch,` par :

```typescript
          branch: branchOrUndefined(v.branch),
```

Dans `_saveEdit` (l.161-165), remplacer `branch: v.branch,` par :

```typescript
            branch: branchOrUndefined(v.branch),
```

(Le type `SourceConfigInput.branch?` rend l'omission — valeur `undefined` non sérialisée en JSON — valide.)

- [ ] **Step 5 : Afficher le toast d'avertissement au succès**

Dans `onSubmitCreate`, le callback `onSuccess` (l.139) reçoit la source créée. Remplacer :

```typescript
        onSuccess: () => {
          toast({ title: t("sources.add.success") });
          createForm.reset();
          onOpenChange(false);
        },
```

par :

```typescript
        onSuccess: (created) => {
          if (created.branch_warning) {
            toast({ title: t("sources.add.branch_warning") });
          }
          toast({ title: t("sources.add.success") });
          createForm.reset();
          onOpenChange(false);
        },
```

- [ ] **Step 6 : Mettre le placeholder sur le champ branche**

Dans `BranchField` (l.368-375), remplacer `<Input {...register("branch")} />` par :

```typescript
      <Input {...register("branch")} placeholder={t("sources.fields.branch_placeholder")} />
```

- [ ] **Step 7 : Lancer les tests, vérifier le succès**

Run: `cd frontend && npm run test:run -- AddSourceDialog`
Expected: PASS — tous les tests AddSourceDialog passent (y compris les 2 nouveaux). Note : le test existant « affiche les champs … Branche » reste vert (le label `Branche` est inchangé).

- [ ] **Step 8 : Vérifier TS strict + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: pas d'erreur.

- [ ] **Step 9 : Commit**

```bash
git add frontend/src/pages/workspace/AddSourceDialog.tsx frontend/src/pages/workspace/__tests__/AddSourceDialog.test.tsx
git commit -m "feat(front): branche optionnelle (auto-détection) + toast d'avertissement"
```

---

## Vérification finale

- [ ] **Backend unit + smoke**

Run: `cd backend && uv run pytest tests/unit tests/smoke -q`
Expected: tous verts (sauf `test_source_create_git_minimal`, échec pré-existant hors scope — cf. ci-dessous).

- [ ] **Backend integration** (Postgres requis — pattern `run-test.sh` / `docs/test.md`)

Run: `cd backend && uv run pytest tests/integration/test_git_ops_branch.py tests/integration/test_services_sources.py -v`
Expected: nouveaux tests branch verts.

- [ ] **Frontend complet**

Run: `cd frontend && npm run test:run`
Expected: pas de nouvelle régression.

---

## Notes / hors scope

- **Test obsolète pré-existant** : `tests/unit/test_schemas_admin.py::test_source_create_git_minimal` échoue déjà (commit `4492f76` a rendu `name`/`api_key_vault` obligatoires). Idem `tests/integration/test_services_sources.py:94,122` qui construisent `SourceCreateRequest` sans ces champs. **Hors scope de cette feature** — à corriger dans un commit `fix(test):` séparé. ⚠️ Si les tests d'intégration des Tasks 4-5 sont lancés avec tout le fichier, ces deux constructions pré-existantes lèveront une `ValidationError` ; les corriger d'abord (ajouter `name=` + `api_key_vault=`) si on veut un run de fichier entièrement vert.
- **`test_source_connection`** : pourrait afficher la branche détectée — amélioration future, non incluse (YAGNI).
- Le défaut backend `executor.py:240` (`config.get("branch", "main")`) reste comme garde-fou ; la branche est désormais toujours résolue à l'écriture, donc ce défaut ne devrait plus servir en pratique.
