from __future__ import annotations

import html
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from rag.indexer.chunking._sections import scan_fences
from rag.indexer.chunking.protocol import Chunk, ChunkerProtocol
from rag.indexer.chunking.structured import ChunkedDocument, StructuredChunkerProtocol


def clean_content_text(text: str) -> str:
    """Nettoyage non-destructif du texte avant chunking.

    Opérations (dans l'ordre) :
    1. Normalisation unicode NFKC — ligatures, espaces spéciaux, apostrophes
    2. CRLF / CR → LF
    3. Suppression des espaces et tabulations en fin de ligne
    4. Maximum 2 lignes vides consécutives

    L'indentation (espaces en début de ligne) est intégralement préservée —
    elle est sémantique pour le code Python/YAML/… Pas de normalisation des
    espaces en milieu de ligne (idem).
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# `~~~` est exclu : c'est un délimiteur de fence de code (géré par scan_fences),
# jamais un séparateur décoratif. Le retirer casserait les régions fencées
# (BUG-039).
_SEP_LINE_RE = re.compile(r"^[ \t]*[-=*_]{3,}[ \t]*$")
_FRONTMATTER_DELIM_RE = re.compile(r"^[ \t]*---[ \t]*$")
_FRONTMATTER_CLOSE = ("---", "...")


def _is_separator_line(line: str) -> bool:
    return bool(_SEP_LINE_RE.match(line))


def _frontmatter_end(lines: list[str]) -> int:
    """Index (exclusif) de fin du frontmatter YAML, ou 0 s'il n'y en a pas.

    Frontmatter = bloc ouvert par une ligne `---` en tout début de document et
    refermé par `---` ou `...`. Ces lignes sont préservées : les délimiteurs ne
    sont pas des séparateurs décoratifs (BUG-039).
    """
    if not lines or not _FRONTMATTER_DELIM_RE.match(lines[0]):
        return 0
    for j in range(1, len(lines)):
        if lines[j].strip() in _FRONTMATTER_CLOSE:
            return j + 1
    return 0


def strip_decorative_separators(text: str) -> str:
    """Supprime les lignes séparatrices décoratives (---, ===, ***, ___).

    Fence-aware : les régions fencées (```/~~~) et le frontmatter YAML sont
    préservés intégralement — leurs délimiteurs ne sont jamais traités comme des
    séparateurs, ce qui inversait sinon les régions fencées du document (BUG-039).

    Préserve aussi les underlines setext Markdown (--- ou === immédiatement après
    une ligne de texte non vide et non-séparateur) pour ne pas casser la détection
    de titres H1/H2.
    """
    lines = text.split("\n")
    fenced: set[int] = set()
    for start, end in scan_fences(lines):
        fenced.update(range(start, end))
    fm_end = _frontmatter_end(lines)
    result: list[str] = []
    for i, line in enumerate(lines):
        if i < fm_end or i in fenced:
            result.append(line)  # frontmatter / région fencée → préservé
        elif _is_separator_line(line):
            prev = lines[i - 1] if i > 0 else ""
            if prev.strip() and not _is_separator_line(prev):
                result.append(line)  # underline setext → préservé
        else:
            result.append(line)
    return "\n".join(result)


_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def strip_html_tags(text: str) -> str:
    """Supprime les balises HTML et décode les entités communes.

    Opérations (dans l'ordre) :
    1. Décodage des entités (&amp;, &lt;, &gt;, &quot;, &apos;, &nbsp;, numériques…)
       via `html.unescape` — sémantique correcte, pas de double-décodage
       (contrairement à un remplacement naïf où `&amp;amp;` redevenait `<`).
    2. Suppression des balises (<tag>, </tag>, <self/>) — le regex exige un nom
       de tag valide en tête (`</?[a-zA-Z]`) pour ne pas avaler la prose
       contenant des comparateurs (`x < y && y > z`) ou des generics (`vector<T>`).

    Les régions fencées (```/~~~) sont préservées telles quelles : le nettoyage
    HTML ne doit pas corrompre des échantillons de code.

    Note : `html.unescape` décode `&nbsp;` en U+00A0 (espace insécable) ; on le
    normalise en espace ordinaire pour ne pas casser la correspondance de mots
    en aval (recherche lexicale, embeddings).
    """
    text = html.unescape(text).replace("\u00a0", " ")
    lines = text.splitlines(keepends=False)
    fence_ranges = scan_fences(lines)
    fenced_line_idx: set[int] = set()
    for start, end in fence_ranges:
        fenced_line_idx.update(range(start, end))
    cleaned_lines = [
        line if i in fenced_line_idx else _HTML_TAG_RE.sub("", line)
        for i, line in enumerate(lines)
    ]
    result = "\n".join(cleaned_lines)
    if text.endswith("\n"):
        result += "\n"
    return result


_BOILERPLATE_RE = re.compile(
    r"auto[- ]?generated"
    r"|do\s+not\s+edit"
    r"|generated\s+by\b"
    r"|this\s+file\s+(?:was|is)\s+(?:auto[- ]?)?generated"
    r"|do\s+not\s+modify"
    r"|spdx-license-identifier"
    r"|spdx-filecopyrighttext"
    r"|copyright\s*\(c\)"
    r"|all\s+rights\s+reserved",
    re.IGNORECASE,
)
_REPEAT_THRESHOLD = 5
_REPEAT_MIN_LEN = 10


def strip_boilerplate_lines(text: str) -> str:
    """Supprime les lignes boilerplate : marqueurs connus + lignes répétées.

    Passe 1 — marqueurs connus (insensible à la casse) :
        auto-generated, do not edit, generated by, SPDX-*, copyright (c),
        all rights reserved, …

    Passe 2 — en-têtes/pieds de page répétés :
        Toute ligne non indentée d'au moins 10 caractères apparaissant 5 fois
        ou plus dans le même document est retirée (heuristique footer/header).
    """
    lines = text.split("\n")
    filtered = [ln for ln in lines if not _BOILERPLATE_RE.search(ln)]
    candidates = [
        ln
        for ln in filtered
        if ln.strip() and not ln[:1].isspace() and len(ln.strip()) >= _REPEAT_MIN_LEN
    ]
    repeated = {ln for ln, n in Counter(candidates).items() if n >= _REPEAT_THRESHOLD}
    if repeated:
        filtered = [ln for ln in filtered if ln not in repeated]
    return "\n".join(filtered)


@dataclass(frozen=True)
class CleaningOptions:
    """Options de nettoyage du contenu avant chunking.

    Chaque option est indépendante et désactivée par défaut — aucun changement
    de comportement pour les stratégies existantes. Activable via
    `chunking_strategies.params` jsonb, une clé à la fois.
    """

    clean_content: bool = False
    strip_separators: bool = False
    strip_boilerplate: bool = False
    strip_html: bool = False

    @property
    def any_enabled(self) -> bool:
        return (
            self.clean_content or self.strip_separators or self.strip_boilerplate or self.strip_html
        )


def apply_cleaning(content: str, options: CleaningOptions) -> str:
    """Applique les nettoyages activés à `content`, dans l'ordre canonique.

    Ordre d'application : strip_html → clean_content → strip_separators →
    strip_boilerplate. Chaque étape est indépendante ; si toutes les options
    sont désactivées, `content` est renvoyé inchangé.
    """
    if options.strip_html:
        content = strip_html_tags(content)
    if options.clean_content:
        content = clean_content_text(content)
    if options.strip_separators:
        content = strip_decorative_separators(content)
    if options.strip_boilerplate:
        content = strip_boilerplate_lines(content)
    return content


class CleaningChunkerWrapper:
    """Applique les nettoyages configurés avant de déléguer au chunker interne.

    Implémente `StructuredChunkerProtocol`. Sans `options`, se comporte comme
    l'ancienne version (clean_content=True) pour la rétro-compatibilité.

    Ordre d'application : strip_html → clean_content → strip_separators → strip_boilerplate.
    """

    def __init__(
        self, inner: StructuredChunkerProtocol, options: CleaningOptions | None = None
    ) -> None:
        self._inner = inner
        self._options = options if options is not None else CleaningOptions(clean_content=True)

    def chunk(self, content: str) -> ChunkedDocument:
        return self._inner.chunk(apply_cleaning(content, self._options))


class CleaningLegacyChunkerWrapper:
    """Équivalent de `CleaningChunkerWrapper` pour le moteur legacy.

    Implémente `ChunkerProtocol` (découpage plat → `list[Chunk]`). Réutilise la
    même logique de nettoyage pré-chunk que le moteur structured via
    `apply_cleaning`, sans dupliquer l'algorithme.
    """

    def __init__(self, inner: ChunkerProtocol, options: CleaningOptions) -> None:
        self._inner = inner
        self._options = options

    def chunk(self, content: str) -> list[Chunk]:
        return self._inner.chunk(apply_cleaning(content, self._options))
