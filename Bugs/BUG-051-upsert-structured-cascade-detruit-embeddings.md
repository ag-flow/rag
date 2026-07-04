# BUG-051 — `upsert_structured` supprime les sections périmées *avant* de re-pointer les chunks gardés → le CASCADE FK détruit silencieusement des embeddings gardés

**Statut : 🔴 à corriger**

- **Zone** : backend / db/workspace_structured
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/db/workspace_structured.py:126-165`, cascade en `workspace_migrations/versions/002_sections_and_chunk_hash.sql`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — ordre d'opérations subtil, perte de données

## Description

Ordre des opérations : (1) supprimer les embeddings dont le hash a disparu, (2) upsert les sections, (3) `DELETE FROM sections WHERE section_key <> ALL(current)` — ce qui **cascade** et supprime tout embedding référençant encore une section retirée — puis (4) la boucle `UPDATE embeddings ... WHERE chunk_hash=$5` pour les enfants gardés (`embedding is None`). Si la section parente d'un chunk gardé a été renommée/retirée, la ligne a déjà été cascade-supprimée à l'étape 3 ; l'étape 4 met à jour 0 ligne, `kept` est quand même incrémenté, et le chunk disparaît sans embedding disponible pour réinsérer.

## Scénario de défaillance

Une section d'un doc markdown est renommée (`## Intro` → `## Overview`) mais le texte normalisé d'un chunk est inchangé → même `chunk_hash` → planifié comme « kept ». Au reindex le chunk disparaît silencieusement de l'index jusqu'à ce que le contenu du fichier lui-même change (diff de hash) — perte de recall silencieuse.

## Code concerné

```python
key_to_id = await _upsert_sections(conn, path, parents)
await conn.execute(
    "DELETE FROM sections WHERE path=$1 AND section_key <> ALL($2::text[])", ...)  # CASCADE ici
...
await conn.execute(
    "UPDATE embeddings SET chunk_index=$2, section_id=$3, ... WHERE path=$1 AND chunk_hash=$5", ...)  # 0 ligne
kept += 1
```

## Piste de correction

Supprimer les sections périmées *après* la boucle des enfants (les enfants gardés obtiennent d'abord leur nouveau `section_id`), ou détecter les updates d'enfants gardés affectant 0 ligne et échouer/re-embed.
