from __future__ import annotations

import asyncio
import fnmatch
import os
import re
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


async def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    error_cls: type[RuntimeError] = RuntimeError,
    error_prefix: str = "git failed",
) -> tuple[str, str]:
    """Exécute git avec stderr capturé + sanitization.

    Lève `error_cls(error_prefix + ": <stderr sanitized>")` sur returncode != 0.
    Retourne `(stdout, stderr)` sanitized en cas de succès.

    `GIT_TERMINAL_PROMPT=0` empêche git d'attendre un mot de passe interactif.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
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
) -> None:
    """`git clone --branch <branch> <auth_url> <dest>`.

    Lève `GitCloneError` (sanitized) si échec.
    """
    auth_url = _build_authenticated_url(url, token)
    dest.parent.mkdir(parents=True, exist_ok=True)
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


async def pull(*, dest: Path, branch: str) -> None:
    """Fetch + reset --hard pour aligner sur remote/<branch>.

    Lève `GitPullError` (sanitized) si fetch ou reset échoue.
    Le `reset --hard` perd les modifs locales — voulu, le worktree est
    contrôlé par le worker uniquement.
    """
    log.info("git.pull.start", dest=str(dest), branch=branch)
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


def filter_glob(
    cs: ChangeSet,
    *,
    include: list[str],
    exclude: list[str],
) -> ChangeSet:
    """Applique les filtres glob (`fnmatch`) sur un ChangeSet.

    Un fichier passe si :
      - il match au moins un pattern `include`
      - ET il ne match aucun pattern `exclude`

    `**/*` est traité comme `*` (récursif sur le worktree).
    """

    def _match(path: str, patterns: list[str]) -> bool:
        for p in patterns:
            # fnmatch supporte * mais pas ** ; on désucre.
            adjusted = p.replace("**/", "").replace("**", "*")
            if fnmatch.fnmatch(path, adjusted):
                return True
        return False

    def _keep(path: str) -> bool:
        if not _match(path, include):
            return False
        return not (exclude and _match(path, exclude))

    return ChangeSet(
        added=[p for p in cs.added if _keep(p)],
        modified=[p for p in cs.modified if _keep(p)],
        deleted=[p for p in cs.deleted if _keep(p)],
    )
