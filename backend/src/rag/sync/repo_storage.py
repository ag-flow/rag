from __future__ import annotations

from pathlib import Path
from uuid import UUID


class RepoStorage:
    """Résolution des chemins locaux pour les clones git par workspace+source.

    Layout :
        <root>/<workspace_id>/<source_id>/
        <root>/<workspace_id>/<source_id>/.git/

    Les UUID sont sérialisés en string canonique (`str(UUID)` → `xxxxxxxx-...`),
    donc inoffensifs côté path injection. `pathlib.Path` empêche toute
    manipulation type `..` dans le segment puisque l'UUID est strictement
    validé en amont par Pydantic.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, *, workspace_id: UUID, source_id: UUID) -> Path:
        return self._root / str(workspace_id) / str(source_id)

    def ensure_exists(self, *, workspace_id: UUID, source_id: UUID) -> Path:
        """Crée le dossier (parents=True) et retourne le path. Idempotent."""
        p = self.path_for(workspace_id=workspace_id, source_id=source_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def has_git(self, *, workspace_id: UUID, source_id: UUID) -> bool:
        """True si `<path>/.git` existe (clone fait au moins une fois)."""
        return (self.path_for(workspace_id=workspace_id, source_id=source_id) / ".git").exists()
