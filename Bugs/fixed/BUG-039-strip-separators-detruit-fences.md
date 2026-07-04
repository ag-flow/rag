# BUG-039 — `strip_separators` détruit les fences de code `~~~` et les délimiteurs de frontmatter `---`

**Statut : 🟢 corrigé**

- **Zone** : backend / indexer/chunking
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/indexer/chunking/cleaner.py:31-52`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — nettoyeur fence-aware, logique subtile

## Description

`_SEP_LINE_RE` matche les lignes `~~~` et `---`. Le nettoyeur ne connaît pas les fences et tourne avant le chunking. Un ouvreur de fence suit typiquement une ligne vide → supprimé ; le fermeur suit du code non vide → gardé (pris pour un underline setext). Le fermeur gardé est alors parsé comme *ouvreur* par `scan_fences`/markdown-it, inversant les régions fencées/non-fencées pour le reste du document. Idem pour le frontmatter YAML (`---` ligne 0 supprimé, `---` fermant gardé) et les séparateurs `---` dans du YAML fencé.

## Scénario de défaillance

Stratégie avec `strip_separators: true` sur un fichier markdown à fences `~~~` : l'ouvreur est retiré, le code fuit dans la prose (word-split, déchiqueté), et tout après le fermeur survivant est traité comme un fence atomique unique — pouvant lever `ChunkTooLargeError` et faire échouer le fichier (cf. BUG-033).

## Code concerné

```python
_SEP_LINE_RE = re.compile(r"^[ \t]*[-=*~_]{3,}[ \t]*$")   # matche fences ~~~ et frontmatter ---
```

## Piste de correction

Rendre le nettoyeur fence-aware (réutiliser `scan_fences` pour sauter les régions fencées) et exclure les délimiteurs `~~~`/frontmatter de la classe séparateur.
