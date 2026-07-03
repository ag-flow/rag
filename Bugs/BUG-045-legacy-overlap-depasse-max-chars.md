# BUG-045 — L'overlap legacy fait dépasser `max_chars` aux chunks

**Statut : 🔴 à corriger**

- **Zone** : backend / indexer/chunking
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/indexer/chunking/paragraph.py:75-79` (lié : `markdown.py:_subsplit_with_fences`)
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

L'overlap est appliqué en préfixant la queue du chunk précédent *après* le découpage en taille, donc les chunks finaux atteignent `max_chars + overlap_chars`. Si `max_chars` est dimensionné sur la limite d'input du provider, les chunks avec overlap la dépassent.

## Scénario de défaillance

`max_chars=8000, overlap_chars=1000` calibrés sur un budget ~8192-tokens : chaque chunk non-premier fait jusqu'à 9000 chars → le provider renvoie 400 sur les workspaces moteur legacy (puis la mauvaise classification du BUG-042 s'enclenche).

## Code concerné

```python
prev_tail = split_chunks[i - 1][-self._overlap_chars :]
result.append(Chunk(content=prev_tail + split_chunks[i]))
```

## Piste de correction

Réserver l'overlap dans le budget de découpage (`max_chars - overlap_chars`), comme le fait déjà le `TokenNormalizer` structuré. Ajouter aussi un contrôle de taille dans `markdown.py:_subsplit_with_fences` (qui émet les fences en chunks uniques sans borne).
