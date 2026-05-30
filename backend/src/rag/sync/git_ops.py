from __future__ import annotations

import asyncio
import contextlib
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

import structlog

from rag.schemas.sync import ChangeSet

log = structlog.get_logger(__name__)


class GitCloneError(RuntimeError):
    """Echec d'un `git clone`."""


class GitPullError(RuntimeError):
    """Echec d'un `git pull` ou `git fetch`/`reset`."""


# Token-in-URL pattern : https://user:token@host... → https://***@host
_TOKEN_URL_RE = re.compile(r"https?://[^@\s]+@", re.IGNORECASE)

# Ligne symref de `git ls-remote --symref <url> HEAD` :
#   "ref: refs/heads/<branch>\tHEAD"
_SYMREF_HEAD_RE = re.compile(r"^ref:\s+refs/heads/(?P<branch>\S+)\s+HEAD", re.MULTILINE)


def _parse_symref_head(stdout: str) -> str | None:
    """Extrait le nom de branche de la ligne symref de `ls-remote --symref HEAD`.

    Retourne None si aucune ligne symref n'est présente.
    """
    match = _SYMREF_HEAD_RE.search(stdout)
    return match.group("branch") if match else None


def sanitize_git_output(text: str) -> str:
    """Remplace tout `https://<user>:<token>@host` par `https://***@host`.

    Appliqué sur stderr/stdout avant tout log ou persistance dans
    `index_jobs.error_message`. Idempotent (déjà sanitized → no-op).
    """
    return _TOKEN_URL_RE.sub("https://***@", text)


def _build_authenticated_url(url: str, token: str | None) -> str:
    """Injecte le token dans une URL HTTPS GitHub/Azure.

    Si `token` est None : URL inchangée (clone anonyme — OK pour repos publics).
    Sinon : `https://x-access-token:<token>@host/...`.
    """
    if token is None:
        return url
    if not url.startswith("https://"):
        return url  # SSH ou git:// — l'auth se fait autrement (clé SSH, etc.)
    return url.replace("https://", f"https://x-access-token:{token}@", 1)


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
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


async def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    error_cls: type[RuntimeError] = RuntimeError,
    error_prefix: str = "git failed",
    extra_env: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Exécute git avec stderr capturé + sanitization.

    Lève `error_cls(error_prefix + ": <stderr sanitized>")` sur returncode != 0.
    Retourne `(stdout, stderr)` sanitized en cas de succès.

    `GIT_TERMINAL_PROMPT=0` empêche git d'attendre un mot de passe interactif.
    """
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
        # cwd absent / invalide → on remonte l'erreur typée attendue.
        raise error_cls(f"{error_prefix}: {sanitize_git_output(str(exc))}") from exc
    stdout_b, stderr_b = await proc.communicate()
    stdout = sanitize_git_output(stdout_b.decode("utf-8", errors="replace"))
    stderr = sanitize_git_output(stderr_b.decode("utf-8", errors="replace"))

    if proc.returncode != 0:
        msg = f"{error_prefix}: {stderr.strip() or stdout.strip() or 'unknown error'}"
        raise error_cls(msg)
    return stdout, stderr


async def clone(
    *,
    url: str,
    branch: str,
    token: str | None,
    dest: Path,
    ssh_key: str | None = None,
    ssh_username: str | None = None,
) -> None:
    """`git clone --branch <branch> <auth_url> <dest>`.

    Lève `GitCloneError` (sanitized) si échec.
    Si `ssh_key` est fourni, l'auth se fait via clé privée temporaire (SSH).
    Sinon, l'auth se fait via token injecté dans l'URL (HTTPS).
    """
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


async def head_commit(dest: Path) -> str:
    """Retourne le SHA-1 du HEAD courant (`git rev-parse HEAD`).

    Lève `GitPullError` (sanitized) si le repo est invalide / corrompu.
    """
    stdout, _ = await _run_git(
        ["rev-parse", "HEAD"],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git rev-parse failed",
    )
    return stdout.strip()


async def pull(*, dest: Path, branch: str, ssh_key: str | None = None) -> None:
    """Fetch + reset --hard pour aligner sur remote/<branch>.

    Lève `GitPullError` (sanitized) si fetch ou reset échoue.
    Le `reset --hard` perd les modifs locales — voulu, le worktree est
    contrôlé par le worker uniquement.
    Si `ssh_key` est fourni, l'auth se fait via clé privée temporaire (SSH).
    """
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


async def detect_default_branch(
    *, url: str, token: str | None, deadline: float = 15.0
) -> str | None:
    """Branche par défaut du remote via `git ls-remote --symref <url> HEAD`.

    Retourne le nom de branche (ex: "main", "master"), ou None si
    indéterminable (échec réseau, timeout, repo injoignable, pas de symref).
    Ne lève jamais : le repli est de la responsabilité de l'appelant.
    """
    auth_url = _build_authenticated_url(url, token)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        async with asyncio.timeout(deadline):
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
            stdout_b, _ = await proc.communicate()
    except (TimeoutError, FileNotFoundError, NotADirectoryError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return _parse_symref_head(stdout_b.decode("utf-8", errors="replace"))


async def list_remote_branches(
    *,
    url: str,
    token: str | None = None,
    ssh_key: str | None = None,
    ssh_username: str | None = None,
    deadline: float = 10.0,
) -> list[str]:
    """`git ls-remote --heads <url>` → liste triée des noms de branches.

    Retourne [] en cas d'erreur (timeout, auth, réseau). Ne lève jamais.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    if ssh_key is not None:
        with _ssh_key_env(ssh_key) as ssh_env:
            env.update(ssh_env)
        auth_url = url
    else:
        auth_url = _build_authenticated_url(url, token)

    try:
        async with asyncio.timeout(deadline):
            proc = await asyncio.create_subprocess_exec(
                "git",
                "ls-remote",
                "--heads",
                auth_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout_b, _ = await proc.communicate()
    except (TimeoutError, FileNotFoundError, NotADirectoryError, OSError):
        return []

    if proc.returncode != 0:
        return []

    branches: list[str] = []
    for line in stdout_b.decode("utf-8", errors="replace").splitlines():
        if "\trefs/heads/" in line:
            branch = line.split("\trefs/heads/", 1)[1].strip()
            if branch:
                branches.append(branch)
    return sorted(branches)


async def list_all_files(dest: Path) -> list[str]:
    """Retourne tous les fichiers trackés par git (`git ls-files`).

    Sert au 1er sync d'une source (pas de `last_commit` connu) : on traite
    tous les fichiers du worktree.
    """
    stdout, _ = await _run_git(
        ["ls-files"],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git ls-files failed",
    )
    return [line for line in stdout.splitlines() if line]


async def diff_changes(
    *,
    dest: Path,
    from_commit: str,
    to_commit: str,
) -> ChangeSet:
    """`git diff --name-status <from>..<to>` → ChangeSet typé.

    Préfixes git : `A` (added), `M` (modified), `D` (deleted),
    `R<score>` (renamed — traité comme delete+add).
    """
    stdout, _ = await _run_git(
        ["diff", "--name-status", f"{from_commit}..{to_commit}"],
        cwd=dest,
        error_cls=GitPullError,
        error_prefix="git diff failed",
    )
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status == "A":
            added.append(parts[1])
        elif status == "M":
            modified.append(parts[1])
        elif status == "D":
            deleted.append(parts[1])
        elif status.startswith("R"):
            # Rename = delete + add
            deleted.append(parts[1])
            added.append(parts[2])
    return ChangeSet(added=added, modified=modified, deleted=deleted)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile un pattern glob (avec `**`) en expression régulière.

    Sémantique :
    - `*`   : n'importe quel caractère sauf `/` (un seul segment)
    - `?`   : un caractère quelconque sauf `/`
    - `**/` : zéro ou plusieurs segments suivis de `/`
    - `**`  : n'importe quoi (y compris `/`) — utilisé en fin de pattern
    - Tout le reste est échappé littéralement.

    Exemples :
    - `**/*.md`          → matche `a.md`, `docs/a.md`, `deep/path/a.md`
    - `**/node_modules/**` → matche `node_modules/x`, `a/b/node_modules/x`
    - `docs/**`          → matche uniquement les chemins commençant par `docs/`
    """
    result: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i] == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            if i + 2 < len(pattern) and pattern[i + 2] == "/":
                # `**/` → zéro ou plusieurs segments avec slash final
                result.append("(.+/)?")
                i += 3
            else:
                # `**` en fin de pattern → n'importe quoi
                result.append(".*")
                i += 2
        elif pattern[i] == "*":
            result.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            result.append("[^/]")
            i += 1
        else:
            result.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(result) + "$")


def filter_glob(
    cs: ChangeSet,
    *,
    include: list[str],
    exclude: list[str],
) -> ChangeSet:
    """Applique les filtres glob sur un ChangeSet.

    Un fichier passe si :
      - il matche au moins un pattern `include`
      - ET il ne matche aucun pattern `exclude`

    Utilise `_glob_to_regex` qui gère `**` correctement :
    `**/node_modules/**` exclut les chemins imbriqués comme
    `tools/md2pdf/node_modules/x.md`, et `**/*.md` matche les `.md`
    à n'importe quelle profondeur y compris à la racine.
    """
    include_re = [_glob_to_regex(p) for p in include]
    exclude_re = [_glob_to_regex(p) for p in exclude]

    def _match(path: str, patterns: list[re.Pattern[str]]) -> bool:
        return any(rx.match(path) for rx in patterns)

    def _keep(path: str) -> bool:
        if not _match(path, include_re):
            return False
        return not (exclude_re and _match(path, exclude_re))

    return ChangeSet(
        added=[p for p in cs.added if _keep(p)],
        modified=[p for p in cs.modified if _keep(p)],
        deleted=[p for p in cs.deleted if _keep(p)],
    )
