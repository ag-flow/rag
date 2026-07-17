from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "rag"

# Chemin job (spec chunking §5, S4.2) : aucun module de la chaîne d'indexation
# autonome ne doit dépendre d'un contexte d'authentification. La résolution
# user-aware vit exclusivement côté API (acceptation du push).
_JOB_MODE_PATHS = [
    SRC / "indexer",
    SRC / "sync",
    SRC / "services" / "chunking_routing.py",
]
_FORBIDDEN = ("rag.auth", "from rag import auth")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for path in _JOB_MODE_PATHS:
        if path.is_file():
            files.append(path)
        else:
            files.extend(sorted(path.rglob("*.py")))
    return files


class TestJobModePurity:
    def test_job_mode_modules_never_import_auth(self) -> None:
        offenders = [
            str(f.relative_to(SRC))
            for f in _python_files()
            if any(marker in f.read_text(encoding="utf-8") for marker in _FORBIDDEN)
        ]
        assert offenders == [], f"contexte d'auth importé dans le chemin job : {offenders}"

    def test_scan_covers_expected_modules(self) -> None:
        files = _python_files()
        names = {f.name for f in files}
        assert "real.py" in names  # indexeur
        assert "executor.py" in names  # worker
        assert "chunking_routing.py" in names  # résolution
        assert len(files) > 10
