# BUG-044 — `scan_fences` ignore la règle de longueur de fence : les fences à 4 backticks se ferment trop tôt

**Statut : 🔴 à corriger**

- **Zone** : backend / indexer/chunking
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/indexer/chunking/_sections.py:88-101`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le check de fermeture est `stripped.startswith(fence_marker)` où `fence_marker = stripped[:3]`. CommonMark exige que la fence fermante soit au moins aussi longue que l'ouvreur ; un fence ouvert avec ```` ```` ```` contenant une ligne ` ``` ` (la façon standard de montrer des exemples de code fencé) est fermé au ` ``` ` interne.

## Scénario de défaillance

Un README documentant la syntaxe markdown avec un fence externe à 4 backticks : le ` ``` ` de l'exemple interne ferme le bloc atomique trop tôt ; le reste de l'exemple est word-split comme prose et la prose suivante peut être capturée comme un faux fence — les chunks ne correspondent plus à la structure du document, les hashes churnent.

## Code concerné

```python
fence_marker = stripped[:3]
...
elif in_fence and stripped.startswith(fence_marker):
```

## Piste de correction

Enregistrer le caractère d'ouvreur *et sa longueur* ; exiger longueur du fermeur ≥ longueur de l'ouvreur et même caractère.
