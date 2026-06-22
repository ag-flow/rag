from __future__ import annotations

_SEP = " > "
_GAP = "\n\n"


def render_breadcrumb(path: list[str], *, depth: int) -> str:
    """Rend le fil d'Ariane hiérarchique des titres.

    `depth` :
      - ``0``  : désactivé → "".
      - ``-1`` : chemin complet.
      - ``N>0`` : N derniers niveaux.

    Les titres vides / blancs sont ignorés. Retourne "" si le chemin est vide.
    """
    if depth < -1:
        raise ValueError(f"depth must be -1, 0 or a positive int, got {depth}")
    if depth == 0:
        return ""
    titles = [t.strip() for t in path if t and t.strip()]
    if not titles:
        return ""
    if depth > 0:
        titles = titles[-depth:]
    return _SEP.join(titles)


def prepend_breadcrumb(content: str, path: list[str], *, depth: int) -> str:
    """Préfixe `content` par le fil d'Ariane (séparé d'une ligne vide).

    Retourne `content` inchangé si le breadcrumb est vide (désactivé ou
    chemin vide). C'est le texte EMBEDDÉ (et donc hashé), pas le texte
    parent stocké brut (cf. ADR 0001 §3, §5).
    """
    crumb = render_breadcrumb(path, depth=depth)
    if not crumb:
        return content
    return f"{crumb}{_GAP}{content}"
