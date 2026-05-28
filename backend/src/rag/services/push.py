from __future__ import annotations

import re

from rag.api.errors import InvalidPath

_PATH_MAX_LEN = 1024
_BAD_SEGMENT = re.compile(r"(^|/)\.\.(/|$)")


def normalize_path(raw: str) -> str:
    """Normalise et valide un path POSIX relatif.

    - remplace ``\\`` par ``/``
    - rejette : NUL byte, leading ``/``, segments ``..``, vide, > 1024 chars
    """
    if "\x00" in raw:
        raise InvalidPath("path_contains_nul")
    p = raw.replace("\\", "/")
    if p.startswith("/"):
        raise InvalidPath("path_must_be_relative")
    if _BAD_SEGMENT.search(p):
        raise InvalidPath("path_traversal_forbidden")
    if not p or len(p) > _PATH_MAX_LEN:
        raise InvalidPath("path_invalid_length")
    return p
