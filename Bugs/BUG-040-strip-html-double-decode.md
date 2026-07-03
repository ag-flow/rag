# BUG-040 — `strip_html_tags` double-décode les entités et supprime la prose entre `<` et `>`

**Statut : 🔴 à corriger**

- **Zone** : backend / indexer/chunking
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/indexer/chunking/cleaner.py:57-87`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Deux problèmes : (a) `&amp;amp;` est remplacé *en premier*, donc les entités échappées double-décodent : `&amp;amp;lt;` → `&amp;lt;` → `<`, et le `<...>` résultant peut ensuite être avalé par le regex de tag. (b) `_HTML_TAG_RE = <[^>]+>` n'est pas restreint à la syntaxe de tag : dans `if a < b and c > d`, il supprime `< b and c >`. Appliqué au document entier (fences incluses), il corrompt les échantillons de code et les maths.

## Scénario de défaillance

`strip_html: true` sur des docs contenant des generics C++ ou des opérateurs de comparaison (`vector<string>`, `x < y && y > z`) supprime silencieusement du contenu avant l'embedding — le retrieval rate, et les sections parentes montrées au LLM diffèrent de la source précisément là où ça compte.

## Code concerné

```python
_NAMED_ENTITIES = {"&amp;amp;": "&amp;", "&amp;lt;": "<", ...}   # &amp;amp; traité en premier → double décode
_HTML_TAG_RE = re.compile(r"<[^>]+>")                # matche "< b and c >"
```

## Piste de correction

Remplacer `&amp;amp;` en dernier ; utiliser la sémantique de `html.unescape` ; resserrer le regex de tag sur des noms de tag valides (`</?[a-zA-Z][^>]*>`) et sauter les régions fencées.
