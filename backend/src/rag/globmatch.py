from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache


@lru_cache(maxsize=512)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile un pattern glob (avec `**`) en expression régulière.

    Sémantique :
    - `*`   : n'importe quel caractère sauf `/` (un seul segment)
    - `?`   : un caractère quelconque sauf `/`
    - `**/` : zéro ou plusieurs segments suivis de `/`
    - `**`  : n'importe quoi (y compris `/`) — utilisé en fin de pattern
    - Tout le reste est échappé littéralement.

    Exemples :
    - `**/*.md`            → matche `a.md`, `docs/a.md`, `deep/path/a.md`
    - `**/node_modules/**` → matche `node_modules/x`, `a/b/node_modules/x`
    - `docs/**`            → matche uniquement les chemins commençant par `docs/`
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


def glob_match(pattern: str, path: str) -> bool:
    """Vrai si `path` (relatif, séparateur `/`) matche le pattern glob."""
    return glob_to_regex(pattern).match(path) is not None


def specificity(pattern: str) -> tuple[int, int]:
    """Score de spécificité d'un pattern, comparable entre patterns.

    Règle de départage entre patterns concurrents qui matchent un même
    chemin : (1) le plus de segments (`/`) gagne — `backlog/**/*.md` bat
    `**/*.md` ; (2) à segments égaux, le pattern le plus long gagne.
    Le départage final (égalité parfaite) revient à l'appelant — par
    convention l'ordre de création (le plus ancien gagne).
    """
    return (pattern.count("/"), len(pattern))


def most_specific_index(patterns: Sequence[str], path: str) -> int | None:
    """Indice du pattern le plus spécifique qui matche `path`, sinon None.

    À égalité de spécificité, le premier de la séquence gagne : l'appelant
    fournit les patterns dans un ordre stable (création croissante).
    """
    best: int | None = None
    for i, pattern in enumerate(patterns):
        if not glob_match(pattern, path):
            continue
        if best is None or specificity(pattern) > specificity(patterns[best]):
            best = i
    return best
