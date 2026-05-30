from __future__ import annotations

import subprocess
from pathlib import Path


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


def add_commit(work_dir: Path, files: dict[str, str], deletes: list[str] | None = None) -> str:
    """Ajoute/modifie/supprime des fichiers dans un work dir et push.
    Retourne le nouveau commit SHA.
    """
    for path, content in files.items():
        full = work_dir / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    for path in deletes or []:
        (work_dir / path).unlink()

    subprocess.run(["git", "-C", str(work_dir), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(work_dir), "commit", "-m", "update"],
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(work_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "-C", str(work_dir), "push", "origin", "main"],
        check=True,
        capture_output=True,
    )
    return sha
