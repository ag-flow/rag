# Source Git Auth par Provider — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la saisie manuelle du PAT dans le dialog source Git par un select de credential (token git ou certificat SSH) depuis les vaults accessibles à l'utilisateur, avec support du clone SSH fonctionnel.

**Architecture:** Nouveaux endpoints cross-vault (`git-credentials/by-host`, `ssh-keys/all`). `SourceCreateRequest` simplifié : `auth_ref` ou `ssh_key_ref` fournis directement (plus d'écriture Harpocrate au create). `git_ops._run_git` étendu avec `extra_env` pour `GIT_SSH_COMMAND`. `executor.py` résout le SSH key au moment du job. Dialog refonte complète.

**Tech Stack:** Python 3.12 / asyncpg / FastAPI / tempfile / React 18 / TypeScript strict / TanStack Query / react-hook-form / zod

---

## Structure des fichiers

### Backend (modifier)
- `backend/src/rag/sync/git_ops.py` — SSH support dans `_run_git`, `clone`, `pull`
- `backend/src/rag/schemas/admin.py` — `SourceCreateRequest` + `SourceUpdateRequest`
- `backend/src/rag/schemas/git_credentials.py` — ajouter `GitCredentialWithVault`
- `backend/src/rag/schemas/ssh_keys.py` — ajouter `SshKeyWithVault`
- `backend/src/rag/services/git_credentials.py` — ajouter `list_git_credentials_by_host`
- `backend/src/rag/services/ssh_keys.py` — ajouter `list_ssh_keys_for_owner`
- `backend/src/rag/services/sources.py` — simplifier `add_source` + `update_source`
- `backend/src/rag/sync/executor.py` — résoudre SSH key dans `_execute_git_job`
- `backend/src/rag/api/admin_git_credentials.py` — `router_global` + `GET /by-host`
- `backend/src/rag/api/admin_ssh_keys.py` — `router_global` + `GET /all`
- `backend/src/rag/main.py` — enregistrer les deux nouveaux routers

### Frontend (modifier)
- `frontend/src/lib/harpocrate-vaults.types.ts`
- `frontend/src/lib/harpocrate-vaults.ts`
- `frontend/src/hooks/useHarpocrateVaults.ts`
- `frontend/src/pages/workspace/AddSourceDialog.tsx`
- `frontend/src/i18n/fr/workspace.json`
- `frontend/src/i18n/en/workspace.json`

---

## Task 1 : git_ops.py — support SSH

**Files:**
- Modify: `backend/src/rag/sync/git_ops.py`
- Test: `backend/tests/unit/test_git_ops_ssh.py`

- [ ] **Écrire les tests (rouge)**

```python
# backend/tests/unit/test_git_ops_ssh.py
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from rag.sync.git_ops import clone, pull


@pytest.mark.asyncio
async def test_clone_ssh_passes_git_ssh_command(tmp_path: Path) -> None:
    """clone() avec ssh_key écrit une clé temp et passe GIT_SSH_COMMAND."""
    captured_env: dict = {}

    async def fake_run(args, *, cwd=None, error_cls=RuntimeError,
                       error_prefix="", extra_env=None):
        if extra_env:
            captured_env.update(extra_env)
        return ("", "")

    with patch("rag.sync.git_ops._run_git", side_effect=fake_run):
        dest = tmp_path / "repo"
        dest.mkdir()
        await clone(
            url="git@github.com:org/repo.git",
            branch="main",
            token=None,
            dest=dest,
            ssh_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n",
            ssh_username="git",
        )

    assert "GIT_SSH_COMMAND" in captured_env
    assert "StrictHostKeyChecking=no" in captured_env["GIT_SSH_COMMAND"]
    assert "BatchMode=yes" in captured_env["GIT_SSH_COMMAND"]


@pytest.mark.asyncio
async def test_clone_ssh_temp_file_cleaned_up(tmp_path: Path) -> None:
    """La clé SSH temp est supprimée après le clone, même en cas d'erreur."""
    created_paths: list[str] = []

    original_run = __import__("rag.sync.git_ops", fromlist=["_run_git"])._run_git

    async def tracking_run(args, *, cwd=None, error_cls=RuntimeError,
                           error_prefix="", extra_env=None):
        if extra_env and "GIT_SSH_COMMAND" in extra_env:
            cmd = extra_env["GIT_SSH_COMMAND"]
            # Extraire le path de la clé depuis -i <path>
            for part in cmd.split():
                if part.endswith(".pem"):
                    created_paths.append(part)
        return ("", "")

    with patch("rag.sync.git_ops._run_git", side_effect=tracking_run):
        dest = tmp_path / "repo2"
        dest.mkdir()
        await clone(
            url="git@github.com:org/repo.git",
            branch="main",
            token=None,
            dest=dest,
            ssh_key="fake_key_content",
            ssh_username="git",
        )

    # Le fichier temp doit avoir été créé puis supprimé
    assert len(created_paths) == 1
    assert not os.path.exists(created_paths[0])


@pytest.mark.asyncio
async def test_clone_without_ssh_uses_token_url(tmp_path: Path) -> None:
    """clone() sans ssh_key utilise le comportement HTTPS token existant."""
    captured_args: list = []

    async def fake_run(args, *, cwd=None, error_cls=RuntimeError,
                       error_prefix="", extra_env=None):
        captured_args.extend(args)
        return ("", "")

    with patch("rag.sync.git_ops._run_git", side_effect=fake_run):
        dest = tmp_path / "repo3"
        dest.mkdir()
        await clone(
            url="https://github.com/org/repo.git",
            branch="main",
            token="mytoken",
            dest=dest,
        )

    # L'URL avec token doit être dans les args (pas de ssh_key)
    url_with_token = next((a for a in captured_args if "x-access-token" in a), None)
    assert url_with_token is not None
```

- [ ] **Vérifier que les tests échouent**

```bash
cd backend && uv run pytest tests/unit/test_git_ops_ssh.py --collect-only 2>&1 | head -10
```

- [ ] **Modifier `backend/src/rag/sync/git_ops.py`**

**1. Ajouter l'import `contextlib` et `tempfile` en tête** (après les imports existants) :

```python
import contextlib
import tempfile
from collections.abc import Iterator
```

**2. Ajouter le context manager `_ssh_key_env` après `_build_authenticated_url`** :

```python
@contextlib.contextmanager
def _ssh_key_env(ssh_key: str) -> Iterator[dict[str, str]]:
    """Écrit la clé SSH dans un fichier temp (chmod 600) et yield l'env GIT_SSH_COMMAND."""
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        ) as f:
            f.write(ssh_key)
            tmp_path = f.name
        os.chmod(tmp_path, 0o600)
        yield {
            "GIT_SSH_COMMAND": (
                f"ssh -i {tmp_path} "
                "-o StrictHostKeyChecking=no "
                "-o BatchMode=yes"
            ),
        }
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
```

**3. Ajouter le paramètre `extra_env` à `_run_git`** :

```python
async def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    error_cls: type[RuntimeError] = RuntimeError,
    error_prefix: str = "git failed",
    extra_env: dict[str, str] | None = None,
) -> tuple[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if extra_env:
        env.update(extra_env)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise error_cls(f"{error_prefix}: {sanitize_git_output(str(exc))}") from exc
    stdout_b, stderr_b = await proc.communicate()
    stdout = sanitize_git_output(stdout_b.decode("utf-8", errors="replace"))
    stderr = sanitize_git_output(stderr_b.decode("utf-8", errors="replace"))
    if proc.returncode != 0:
        msg = f"{error_prefix}: {stderr.strip() or stdout.strip() or 'unknown error'}"
        raise error_cls(msg)
    return stdout, stderr
```

**4. Modifier `clone` pour accepter `ssh_key` et `ssh_username`** :

```python
async def clone(
    *,
    url: str,
    branch: str,
    token: str | None,
    dest: Path,
    ssh_key: str | None = None,
    ssh_username: str | None = None,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)

    if ssh_key is not None:
        with _ssh_key_env(ssh_key) as ssh_env:
            log.info("git.clone.start", url=sanitize_git_output(url), dest=str(dest))
            await _run_git(
                ["clone", "--branch", branch, url, str(dest)],
                error_cls=GitCloneError,
                error_prefix="git clone failed",
                extra_env=ssh_env,
            )
    else:
        auth_url = _build_authenticated_url(url, token)
        log.info("git.clone.start", url=sanitize_git_output(auth_url), dest=str(dest))
        await _run_git(
            ["clone", "--branch", branch, auth_url, str(dest)],
            error_cls=GitCloneError,
            error_prefix="git clone failed",
        )
    log.info("git.clone.done", dest=str(dest))
```

**5. Modifier `pull` pour accepter `ssh_key`** :

```python
async def pull(*, dest: Path, branch: str, ssh_key: str | None = None) -> None:
    log.info("git.pull.start", dest=str(dest), branch=branch)

    if ssh_key is not None:
        with _ssh_key_env(ssh_key) as ssh_env:
            await _run_git(
                ["fetch", "origin", branch],
                cwd=dest,
                error_cls=GitPullError,
                error_prefix="git fetch failed",
                extra_env=ssh_env,
            )
            await _run_git(
                ["reset", "--hard", f"origin/{branch}"],
                cwd=dest,
                error_cls=GitPullError,
                error_prefix="git reset failed",
                extra_env=ssh_env,
            )
    else:
        await _run_git(
            ["fetch", "origin", branch],
            cwd=dest,
            error_cls=GitPullError,
            error_prefix="git fetch failed",
        )
        await _run_git(
            ["reset", "--hard", f"origin/{branch}"],
            cwd=dest,
            error_cls=GitPullError,
            error_prefix="git reset failed",
        )
    log.info("git.pull.done", dest=str(dest), branch=branch)
```

- [ ] **Vérifier que les tests passent**

```bash
cd backend && uv run pytest tests/unit/test_git_ops_ssh.py -v
```

Résultat attendu : 3 tests PASS.

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/sync/git_ops.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/sync/git_ops.py backend/tests/unit/test_git_ops_ssh.py
git commit -m "feat(git_ops): support SSH clone/pull via clé privée temp + GIT_SSH_COMMAND"
```

---

## Task 2 : Nouveaux schémas + fonctions de service

**Files:**
- Modify: `backend/src/rag/schemas/git_credentials.py`
- Modify: `backend/src/rag/schemas/ssh_keys.py`
- Modify: `backend/src/rag/services/git_credentials.py`
- Modify: `backend/src/rag/services/ssh_keys.py`

- [ ] **Ajouter `GitCredentialWithVault` dans `backend/src/rag/schemas/git_credentials.py`**

```python
class GitCredentialWithVault(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    host: str
    harpo_path: str
    vault_name: str
    vault_label: str
    created_at: datetime
```

- [ ] **Ajouter `SshKeyWithVault` dans `backend/src/rag/schemas/ssh_keys.py`**

```python
class SshKeyWithVault(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    name: str
    key_type: str
    public_key: str
    passphrase_protected: bool
    harpo_path: str
    vault_name: str
    vault_label: str
    created_at: datetime
```

- [ ] **Ajouter `list_git_credentials_by_host` dans `backend/src/rag/services/git_credentials.py`**

```python
async def list_git_credentials_by_host(
    conn: asyncpg.Connection,
    *,
    owner_id: str,
    host: str,
) -> list[dict]:
    """Retourne les git_credentials pour `host` des vaults accessibles à `owner_id`."""
    rows = await conn.fetch(
        "SELECT gc.id, gc.key_id, gc.label, gc.host, gc.harpo_path, gc.created_at, "
        "v.name AS vault_name, v.label AS vault_label "
        "FROM git_credentials gc "
        "JOIN harpocrate_vaults v ON v.id = gc.vault_id "
        "WHERE gc.host = $1 "
        "AND (v.is_default = true OR v.owner_id = $2) "
        "ORDER BY v.name, gc.key_id",
        host,
        owner_id,
    )
    return [dict(r) for r in rows]
```

- [ ] **Ajouter `list_ssh_keys_for_owner` dans `backend/src/rag/services/ssh_keys.py`**

```python
async def list_ssh_keys_for_owner(
    conn: asyncpg.Connection,
    *,
    owner_id: str,
) -> list[dict]:
    """Retourne toutes les ssh_keys des vaults accessibles à `owner_id`."""
    rows = await conn.fetch(
        "SELECT sk.id, sk.key_id, sk.name, sk.key_type, sk.public_key, "
        "sk.passphrase_protected, sk.harpo_path, sk.created_at, "
        "v.name AS vault_name, v.label AS vault_label "
        "FROM ssh_keys sk "
        "JOIN harpocrate_vaults v ON v.id = sk.vault_id "
        "WHERE v.is_default = true OR v.owner_id = $1 "
        "ORDER BY v.name, sk.key_id",
        owner_id,
    )
    return [dict(r) for r in rows]
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/schemas/git_credentials.py src/rag/schemas/ssh_keys.py src/rag/services/git_credentials.py src/rag/services/ssh_keys.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/git_credentials.py \
        backend/src/rag/schemas/ssh_keys.py \
        backend/src/rag/services/git_credentials.py \
        backend/src/rag/services/ssh_keys.py
git commit -m "feat(schemas+services): GitCredentialWithVault + SshKeyWithVault + list by host/owner"
```

---

## Task 3 : Nouveaux endpoints + main.py

**Files:**
- Modify: `backend/src/rag/api/admin_git_credentials.py`
- Modify: `backend/src/rag/api/admin_ssh_keys.py`
- Modify: `backend/src/rag/main.py`

- [ ] **Ajouter `router_global` dans `backend/src/rag/api/admin_git_credentials.py`**

Ajouter les imports :
```python
from rag.auth.owner import get_current_owner_id
from rag.schemas.git_credentials import GitCredentialWithVault
from rag.services.git_credentials import list_git_credentials_by_host
```

Ajouter après le `router` existant :

```python
router_global = APIRouter(
    prefix="/api/admin/git-credentials",
    tags=["admin-git-credentials"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


@router_global.get("/by-host", response_model=list[GitCredentialWithVault])
async def list_by_host(
    host: str,
    request: Request,
) -> list[GitCredentialWithVault]:
    pool = _pool(request)
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        rows = await list_git_credentials_by_host(conn, owner_id=owner_id, host=host)
    return [GitCredentialWithVault.model_validate(r) for r in rows]
```

- [ ] **Ajouter `router_global` dans `backend/src/rag/api/admin_ssh_keys.py`**

Ajouter les imports :
```python
from rag.auth.owner import get_current_owner_id
from rag.schemas.ssh_keys import SshKeyWithVault
from rag.services.ssh_keys import list_ssh_keys_for_owner
```

Ajouter après le `router` existant :

```python
router_global = APIRouter(
    prefix="/api/admin/ssh-keys",
    tags=["admin-ssh-keys"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


@router_global.get("/all", response_model=list[SshKeyWithVault])
async def list_all_for_owner(
    request: Request,
) -> list[SshKeyWithVault]:
    pool = _pool(request)
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        rows = await list_ssh_keys_for_owner(conn, owner_id=owner_id)
    return [SshKeyWithVault.model_validate(r) for r in rows]
```

- [ ] **Enregistrer dans `main.py`**

Après les imports existants des routers git/ssh, ajouter :

```python
from rag.api.admin_git_credentials import router_global as admin_git_creds_global_router
from rag.api.admin_ssh_keys import router_global as admin_ssh_keys_global_router
```

Après les `app.include_router` existants :

```python
app.include_router(admin_git_creds_global_router)
app.include_router(admin_ssh_keys_global_router)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/admin_git_credentials.py src/rag/api/admin_ssh_keys.py src/rag/main.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin_git_credentials.py \
        backend/src/rag/api/admin_ssh_keys.py \
        backend/src/rag/main.py
git commit -m "feat(api): GET /git-credentials/by-host + GET /ssh-keys/all (cross-vault)"
```

---

## Task 4 : Schemas SourceCreateRequest + SourceUpdateRequest

**Files:**
- Modify: `backend/src/rag/schemas/admin.py`

- [ ] **Lire `backend/src/rag/schemas/admin.py` en entier**

- [ ] **Remplacer `SourceCreateRequest`**

```python
class SourceCreateRequest(BaseModel):
    """Payload POST /workspaces/{name}/sources."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, pattern=r"^[a-z0-9_-]+$")
    type: Literal["git"]
    git_provider: str | None = None
    auth_type: Literal["token", "ssh"] | None = None
    auth_ref: str | None = None
    ssh_key_ref: str | None = None
    ssh_username: str | None = None
    config: dict[str, Any]

    @field_validator("config")
    @classmethod
    def config_must_have_url(cls, v: dict[str, Any]) -> dict[str, Any]:
        if "url" not in v or not v["url"]:
            raise ValueError("config.url is required for git sources")
        return v
```

- [ ] **Remplacer `SourceUpdateRequest`**

```python
class SourceUpdateRequest(BaseModel):
    """Payload PATCH /workspaces/{name}/sources/{source_id}."""

    model_config = ConfigDict(extra="forbid")

    git_provider: str | None = None
    auth_type: Literal["token", "ssh"] | None = None
    auth_ref: str | None = None
    ssh_key_ref: str | None = None
    ssh_username: str | None = None
    config: dict[str, Any]
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/schemas/admin.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/admin.py
git commit -m "feat(schemas): SourceCreateRequest + SourceUpdateRequest — auth_ref + ssh_key_ref"
```

---

## Task 5 : Service sources.py — simplification

**Files:**
- Modify: `backend/src/rag/services/sources.py`

- [ ] **Lire `backend/src/rag/services/sources.py` en entier avant de modifier**

- [ ] **Réécrire `add_source`**

La nouvelle version ne stocke plus rien dans Harpocrate. Elle stocke directement `auth_ref` ou `ssh_key_ref` dans le config JSONB.

```python
async def add_source(
    *,
    workspace_name: str,
    request: SourceCreateRequest,
    config_pool: asyncpg.Pool,
    harpocrate_vaults_service: HarpocrateVaultsService,
) -> dict[str, Any]:
    if request.type != "git":
        raise SourceTypeNotSupported(request.type)

    ws_id = await _get_workspace_id_or_raise(config_pool, workspace_name)
    config = dict(request.config)

    if request.git_provider:
        config["git_provider"] = request.git_provider
    if request.auth_type:
        config["auth_type"] = request.auth_type
    if request.auth_ref:
        config["auth_ref"] = request.auth_ref
    if request.ssh_key_ref:
        config["ssh_key_ref"] = request.ssh_key_ref
    if request.ssh_username:
        config["ssh_username"] = request.ssh_username

    # token pour detect_default_branch : None si SSH (fallback "main" acceptable)
    detect_token: str | None = None
    config, branch_warning = await _resolve_branch_for_write(config, token=detect_token)

    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO workspace_sources (workspace_id, name, type, config, next_sync_at)
            VALUES ($1, $2, $3, $4::jsonb, now())
            RETURNING id, name, type, config, last_indexed_at, created_at
            """,
            ws_id,
            request.name,
            request.type,
            json.dumps(config),
        )

    if row is None:
        raise RuntimeError("unexpected None from RETURNING")
    log.info("source.added", workspace=workspace_name, source_id=str(row["id"]))
    result = _source_to_dict(row)
    result["branch_warning"] = branch_warning
    return result
```

- [ ] **Réécrire `update_source`**

La nouvelle version préserve les champs auth existants si non fournis, remplace si fournis.

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
    ws_id = await _get_workspace_id_or_raise(config_pool, workspace_name)

    current = await fetch_one(
        config_pool,
        """
        SELECT ws.name, ws.config
        FROM workspace_sources ws
        WHERE ws.id = $1::uuid AND ws.workspace_id = $2
        """,
        source_id,
        ws_id,
    )
    if current is None:
        raise SourceNotFound(source_id)

    raw = current["config"]
    current_config = json.loads(raw) if isinstance(raw, str) else dict(raw)

    config = dict(request.config)

    # Préserver les champs auth existants si non fournis
    for field in ("git_provider", "auth_type", "auth_ref", "ssh_key_ref", "ssh_username"):
        new_val = getattr(request, field, None)
        if new_val is not None:
            config[field] = new_val
        elif field in current_config:
            config[field] = current_config[field]

    config, _ = await _resolve_branch_for_write(config, token=None)

    async with config_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE workspace_sources
            SET config = $1::jsonb
            WHERE id = $2::uuid AND workspace_id = $3
            RETURNING id, name, type, config, last_indexed_at, created_at
            """,
            json.dumps(config),
            source_id,
            ws_id,
        )

    if row is None:
        raise SourceNotFound(source_id)
    log.info("source.updated", workspace=workspace_name, source_id=source_id)
    return _source_to_dict(row)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/services/sources.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/sources.py
git commit -m "feat(services): sources.add/update — auth_ref/ssh_key_ref direct, plus d'écriture Harpocrate"
```

---

## Task 6 : executor.py — résolution SSH key au moment du job

**Files:**
- Modify: `backend/src/rag/sync/executor.py`

- [ ] **Lire `backend/src/rag/sync/executor.py` (la fonction `_execute_git_job`) avant de modifier**

- [ ] **Ajouter la résolution SSH dans `_execute_git_job`**

Dans `_execute_git_job`, après la résolution du token (bloc `_resolve_token`), ajouter la résolution SSH :

```python
# Résolution auth : token OU ssh_key
auth_type = config.get("auth_type", "token")

token: str | None = None
ssh_key: str | None = None
ssh_username: str | None = config.get("ssh_username", "git")

if auth_type == "ssh":
    ssh_key_ref = config.get("ssh_key_ref")
    if ssh_key_ref:
        if is_vault_ref(ssh_key_ref):
            ssh_key = await resolver.resolve_with_retry(ssh_key_ref)
        else:
            ssh_key = await resolver.resolve_with_retry(
                _to_vault_ref(ssh_key_ref, default_vault_name)
            )
        _log("info", "Auth : clé SSH résolue.")
    else:
        _log("info", "Auth : source publique (SSH sans clé).")
else:
    if config.get("auth_ref") and default_vault_name is None:
        raise RuntimeError("no default Harpocrate vault configured")
    token = (
        await _resolve_token(resolver, config, default_vault_name)
        if default_vault_name is not None
        else None
    )
    if token:
        _log("info", "Auth : token résolu.")
    else:
        _log("info", "Auth : source publique.")
```

Remplacer les appels `clone(...)` et `pull(...)` pour passer `ssh_key` et `ssh_username` :

```python
# Clone
await clone(
    url=url,
    branch=branch,
    token=token,
    dest=dest,
    ssh_key=ssh_key,
    ssh_username=ssh_username,
)

# Pull
await pull(dest=dest, branch=branch, ssh_key=ssh_key)
```

Supprimer le bloc existant qui calculait `token` avec `_resolve_token` (remplacé par le bloc ci-dessus).

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/sync/executor.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/sync/executor.py
git commit -m "feat(executor): résolution SSH key dans _execute_git_job"
```

---

## Task 7 : Frontend — types + API client + hooks + i18n

**Files:**
- Modify: `frontend/src/lib/harpocrate-vaults.types.ts`
- Modify: `frontend/src/lib/harpocrate-vaults.ts`
- Modify: `frontend/src/hooks/useHarpocrateVaults.ts`
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Ajouter les types dans `harpocrate-vaults.types.ts`**

```typescript
export type GitCredentialWithVault = {
  id: string;
  key_id: string;
  label: string;
  host: string;
  harpo_path: string;
  vault_name: string;
  vault_label: string;
  created_at: string;
};

export type SshKeyWithVault = {
  id: string;
  key_id: string;
  name: string;
  key_type: string;
  public_key: string;
  passphrase_protected: boolean;
  harpo_path: string;
  vault_name: string;
  vault_label: string;
  created_at: string;
};
```

- [ ] **Ajouter les fonctions API dans `harpocrate-vaults.ts`**

Ajouter dans `harpocrateVaultsApi` :

```typescript
  listGitCredentialsByHost: (host: string) =>
    api.get<GitCredentialWithVault[]>(
      `/api/admin/git-credentials/by-host?host=${encodeURIComponent(host)}`
    ),

  listSshKeysAll: () =>
    api.get<SshKeyWithVault[]>(`/api/admin/ssh-keys/all`),
```

- [ ] **Ajouter les hooks dans `useHarpocrateVaults.ts`**

```typescript
export function useGitCredentialsByHost(host: string | null) {
  return useQuery({
    queryKey: ["git-credentials-by-host", host],
    queryFn: () => harpocrateVaultsApi.listGitCredentialsByHost(host!),
    enabled: !!host,
    staleTime: 30_000,
  });
}

export function useSshKeysAll() {
  return useQuery({
    queryKey: ["ssh-keys-all"],
    queryFn: () => harpocrateVaultsApi.listSshKeysAll(),
    staleTime: 30_000,
  });
}
```

- [ ] **Ajouter les clés i18n dans `frontend/src/i18n/fr/workspace.json`**

Dans l'objet `sources.fields`, ajouter :

```json
"git_provider": "Provider Git",
"auth_type": "Authentification",
"auth_type_token": "Token",
"auth_type_ssh": "Certificat SSH",
"credential": "Credential",
"credential_placeholder": "Sélectionner...",
"credential_none": "Aucun credential disponible pour ce provider",
"ssh_username": "Utilisateur SSH",
"ssh_username_placeholder": "git"
```

- [ ] **Ajouter les clés i18n dans `frontend/src/i18n/en/workspace.json`**

```json
"git_provider": "Git Provider",
"auth_type": "Authentication",
"auth_type_token": "Token",
"auth_type_ssh": "SSH Certificate",
"credential": "Credential",
"credential_placeholder": "Select...",
"credential_none": "No credential available for this provider",
"ssh_username": "SSH username",
"ssh_username_placeholder": "git"
```

- [ ] **Vérifier TypeScript + JSON**

```bash
cd frontend && npx tsc --noEmit
node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/workspace.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/en/workspace.json','utf8')); console.log('OK')"
```

- [ ] **Commit**

```bash
git add frontend/src/lib/harpocrate-vaults.types.ts \
        frontend/src/lib/harpocrate-vaults.ts \
        frontend/src/hooks/useHarpocrateVaults.ts \
        frontend/src/i18n/fr/workspace.json \
        frontend/src/i18n/en/workspace.json
git commit -m "feat(front): GitCredentialWithVault + SshKeyWithVault + hooks + i18n source auth"
```

---

## Task 8 : AddSourceDialog — réécriture

**Files:**
- Modify: `frontend/src/pages/workspace/AddSourceDialog.tsx`

- [ ] **Réécrire `frontend/src/pages/workspace/AddSourceDialog.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/useToast";
import { useAddSource, useUpdateSource, useTestSourceConnection } from "@/hooks/useWorkspaces";
import {
  useGitCredentialsByHost,
  useSshKeysAll,
} from "@/hooks/useHarpocrateVaults";
import type { Source } from "@/lib/workspaces.types";

type GitProvider = "github" | "gitlab" | "gitea" | "bitbucket" | "azure-devops";
type AuthType = "token" | "ssh";

const GIT_PROVIDERS: { value: GitProvider; label: string }[] = [
  { value: "github", label: "GitHub" },
  { value: "gitlab", label: "GitLab" },
  { value: "gitea", label: "Gitea" },
  { value: "bitbucket", label: "Bitbucket" },
  { value: "azure-devops", label: "Azure DevOps" },
];

const DEFAULT_SSH_USER: Record<GitProvider, string> = {
  github: "git",
  gitlab: "git",
  gitea: "",
  bitbucket: "git",
  "azure-devops": "",
};

const createSchema = z.object({
  source_name: z.string().min(1).regex(/^[a-z0-9_-]+$/, "invalid_slug"),
  url: z.string().url("invalid_url"),
  branch: z.string().optional(),
  git_provider: z.string().min(1, "required"),
  auth_type: z.enum(["token", "ssh"]),
  credential_ref: z.string().optional(),
  ssh_username: z.string().optional(),
  include: z.string().optional(),
  exclude: z.string().optional(),
});

const editSchema = z.object({
  url: z.string().url("invalid_url"),
  branch: z.string().optional(),
  git_provider: z.string().optional(),
  auth_type: z.enum(["token", "ssh"]).optional(),
  credential_ref: z.string().optional(),
  ssh_username: z.string().optional(),
  include: z.string().optional(),
  exclude: z.string().optional(),
});

type CreateValues = z.infer<typeof createSchema>;
type EditValues = z.infer<typeof editSchema>;

const splitCsv = (s: string | undefined): string[] =>
  (s ?? "").split(",").map((x) => x.trim()).filter(Boolean);

const branchOrUndefined = (b: string | undefined): string | undefined => {
  const trimmed = (b ?? "").trim();
  return trimmed === "" ? undefined : trimmed;
};

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  source?: Source;
}

export function AddSourceDialog({ name, open, onOpenChange, source }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const add = useAddSource(name);
  const update = useUpdateSource(name);
  const testConnection = useTestSourceConnection(name);
  const isEdit = source !== undefined;
  const [testResult, setTestResult] = useState<{ success: boolean; message: string | null } | null>(null);

  const createForm = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      source_name: "",
      url: "",
      branch: "",
      git_provider: "github",
      auth_type: "token",
      credential_ref: "",
      ssh_username: "git",
      include: "",
      exclude: "",
    },
  });

  const editForm = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      url: "",
      branch: "",
      git_provider: "github",
      auth_type: "token",
      credential_ref: "",
      ssh_username: "git",
      include: "",
      exclude: "",
    },
  });

  const activeForm = isEdit ? editForm : createForm;
  const watchedProvider = activeForm.watch("git_provider") as GitProvider | undefined;
  const watchedAuthType = activeForm.watch("auth_type") as AuthType | undefined;

  const { data: gitTokens = [] } = useGitCredentialsByHost(
    watchedAuthType === "token" && watchedProvider ? watchedProvider : null
  );
  const { data: sshKeys = [] } = useSshKeysAll();

  useEffect(() => {
    if (!open) return;
    setTestResult(null);
    if (isEdit && source) {
      const cfg = source.config as Record<string, any>;
      editForm.reset({
        url: cfg.url ?? "",
        branch: cfg.branch ?? "",
        git_provider: (cfg.git_provider as GitProvider) ?? "github",
        auth_type: (cfg.auth_type as AuthType) ?? "token",
        credential_ref: cfg.auth_ref ?? cfg.ssh_key_ref ?? "",
        ssh_username: cfg.ssh_username ?? "git",
        include: (cfg.include ?? []).join(", "),
        exclude: (cfg.exclude ?? []).join(", "),
      });
    } else {
      createForm.reset({
        source_name: "",
        url: "",
        branch: "",
        git_provider: "github",
        auth_type: "token",
        credential_ref: "",
        ssh_username: "git",
        include: "",
        exclude: "",
      });
    }
  }, [open, source, isEdit, createForm, editForm]);

  // Pré-remplir ssh_username quand provider change
  useEffect(() => {
    if (watchedProvider && watchedAuthType === "ssh") {
      const defaultUser = DEFAULT_SSH_USER[watchedProvider] ?? "";
      activeForm.setValue("ssh_username", defaultUser);
    }
  }, [watchedProvider, watchedAuthType, activeForm]);

  function buildPayload(v: CreateValues | EditValues) {
    const branch = branchOrUndefined(v.branch);
    const authType = v.auth_type ?? "token";
    return {
      git_provider: v.git_provider ?? undefined,
      auth_type: authType,
      auth_ref: authType === "token" ? (v.credential_ref || undefined) : undefined,
      ssh_key_ref: authType === "ssh" ? (v.credential_ref || undefined) : undefined,
      ssh_username: authType === "ssh" ? (v.ssh_username || undefined) : undefined,
      config: {
        url: v.url,
        ...(branch !== undefined && { branch }),
        include: splitCsv(v.include),
        exclude: splitCsv(v.exclude),
      },
    };
  }

  const onSubmitCreate = (v: CreateValues) => {
    add.mutate(
      { name: v.source_name, type: "git", ...buildPayload(v) } as any,
      {
        onSuccess: (created) => {
          if ((created as any).branch_warning) {
            toast({ title: t("sources.add.branch_warning") });
          }
          toast({ title: t("sources.add.success") });
          createForm.reset();
          onOpenChange(false);
        },
        onError: () => toast({ title: t("sources.add.error"), variant: "destructive" }),
      }
    );
  };

  const onSubmitEdit = (v: EditValues) => _saveEdit(v, { andThen: "close" });

  const _saveEdit = (v: EditValues, opts: { andThen: "close" | "test" }) => {
    update.mutate(
      { sourceId: source!.id, payload: buildPayload(v) as any },
      {
        onSuccess: () => {
          if (opts.andThen === "close") {
            toast({ title: t("sources.edit.success") });
            onOpenChange(false);
          } else {
            setTestResult(null);
            testConnection.mutate(source!.id, {
              onSuccess: (r) => setTestResult(r),
              onError: () => setTestResult({ success: false, message: t("sources.test.error") }),
            });
          }
        },
        onError: () => toast({ title: t("sources.edit.error"), variant: "destructive" }),
      }
    );
  };

  const isPending = isEdit ? update.isPending : add.isPending;
  const title = isEdit ? t("sources.edit.title") : t("sources.add.title");
  const submitLabel = isEdit ? t("sources.edit.submit") : t("sources.add.submit");

  const { register, handleSubmit, formState, control } = isEdit
    ? editForm
    : createForm;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={handleSubmit(isEdit ? (onSubmitEdit as any) : (onSubmitCreate as any))}
          className="space-y-3"
        >
          {!isEdit && (
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("sources.fields.source_name")}
              </label>
              <Input
                {...(register as any)("source_name")}
                placeholder={t("sources.fields.source_name_placeholder")}
              />
              {(formState.errors as any).source_name && (
                <p className="text-xs text-red-600">
                  {t(`sources.add.errors.${(formState.errors as any).source_name.message ?? "invalid"}`,
                    t("sources.fields.source_name_hint"))}
                </p>
              )}
              <p className="text-xs text-slate-400 mt-0.5">{t("sources.fields.source_name_hint")}</p>
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.url")}</label>
            <Input {...(register as any)("url")} placeholder="https://github.com/..." />
            {(formState.errors as any).url && (
              <p className="text-xs text-red-600">
                {t(`sources.add.errors.${(formState.errors as any).url.message ?? "invalid"}`)}
              </p>
            )}
          </div>

          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.branch")}</label>
            <Input {...(register as any)("branch")} placeholder={t("sources.fields.branch_placeholder")} />
          </div>

          {/* ─── Auth block ─────────────────────────────────── */}
          <div className="rounded-md border bg-slate-50 p-3 space-y-3">
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("sources.fields.git_provider")}
              </label>
              <Controller
                name="git_provider"
                control={control}
                render={({ field }) => (
                  <Select value={field.value ?? ""} onValueChange={field.onChange}>
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {GIT_PROVIDERS.map((p) => (
                        <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("sources.fields.auth_type")}
              </label>
              <Controller
                name="auth_type"
                control={control}
                render={({ field }) => (
                  <div className="flex gap-4 mt-1">
                    {(["token", "ssh"] as AuthType[]).map((at) => (
                      <label key={at} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="radio"
                          value={at}
                          checked={field.value === at}
                          onChange={() => field.onChange(at)}
                        />
                        {at === "token" ? t("sources.fields.auth_type_token") : t("sources.fields.auth_type_ssh")}
                      </label>
                    ))}
                  </div>
                )}
              />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("sources.fields.credential")}
              </label>
              <Controller
                name="credential_ref"
                control={control}
                render={({ field }) => {
                  const items = watchedAuthType === "ssh"
                    ? sshKeys.map((k) => ({
                        value: k.harpo_path,
                        label: k.name,
                        sub: `${k.vault_label} · ${k.key_id} (${k.key_type})`,
                      }))
                    : gitTokens.map((g) => ({
                        value: g.harpo_path,
                        label: g.label,
                        sub: `${g.vault_label} · ${g.key_id}`,
                      }));
                  return items.length === 0 ? (
                    <p className="text-xs text-amber-600 mt-1">{t("sources.fields.credential_none")}</p>
                  ) : (
                    <Select value={field.value ?? ""} onValueChange={field.onChange}>
                      <SelectTrigger className="mt-1">
                        <SelectValue placeholder={t("sources.fields.credential_placeholder")} />
                      </SelectTrigger>
                      <SelectContent>
                        {items.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            <span className="font-medium">{item.label}</span>
                            <span className="ml-2 text-xs text-slate-400">{item.sub}</span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  );
                }}
              />
            </div>

            {watchedAuthType === "ssh" && (
              <div>
                <label className="text-xs font-medium text-slate-700">
                  {t("sources.fields.ssh_username")}
                </label>
                <Input
                  {...(register as any)("ssh_username")}
                  placeholder={t("sources.fields.ssh_username_placeholder")}
                  className="mt-1"
                />
              </div>
            )}
          </div>

          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.include")} <span className="text-slate-400">(csv)</span>
            </label>
            <Input {...(register as any)("include")} placeholder="**/*.md, docs/**" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.exclude")} <span className="text-slate-400">(csv)</span>
            </label>
            <Input {...(register as any)("exclude")} placeholder="**/node_modules/**" />
          </div>

          {testResult !== null && (
            <p
              className={`text-xs px-2 py-1 rounded ${
                testResult.success ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
              }`}
            >
              {testResult.success
                ? t("sources.test.success")
                : `${t("sources.test.failure")} ${testResult.message ?? ""}`}
            </p>
          )}

          <DialogFooter className="gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("dialog.cancel")}
            </Button>
            {isEdit && (
              <Button
                type="button"
                variant="outline"
                disabled={update.isPending || testConnection.isPending}
                onClick={handleSubmit((v) => _saveEdit(v as EditValues, { andThen: "test" }))}
              >
                {update.isPending || testConnection.isPending
                  ? t("sources.test.testing")
                  : t("sources.test.button")}
              </Button>
            )}
            <Button type="submit" disabled={isPending}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/AddSourceDialog.tsx
git commit -m "feat(front): AddSourceDialog — provider + token/SSH credential select"
```
