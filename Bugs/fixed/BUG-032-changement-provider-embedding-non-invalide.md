# BUG-032 — Changer le provider/modèle d'embedding n'invalide jamais les embeddings existants : vecteurs périmés et mixtes

**Statut : 🟢 corrigé**

- **Zone** : backend / sync + indexer + db
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/sync/executor.py:268,756`, `backend/src/rag/db/workspace_structured.py:82-89`, `backend/src/rag/indexer/real.py:210-220`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — logique multi-fichiers, cohérence des espaces vectoriels

## Description

`indexer_used` est stocké expressément pour « invalider les hashes si l'indexeur change » (`indexer/protocol.py:34`), mais la logique de skip ne compare que `content_hash`, jamais `indexer_used`. De plus, le diff structuré (`load_existing_chunk_hashes` + `plan_children`) clé la réutilisation de chunk uniquement sur le sha256 du texte d'embed, sans dimension modèle.

## Scénario de défaillance

L'admin passe `indexer_configs` de `openai/text-embedding-3-small` à `voyage/voyage-3`. Sync suivant : tous les fichiers inchangés sont `skipped` (hash match) et gardent les vecteurs de l'ancien modèle ; les fichiers modifiés réutilisent les chunks « kept » embeddés avec l'ancien modèle tout en insérant de nouveaux chunks avec le nouveau — la même table `embeddings` mélange les espaces vectoriels. Les requêtes embeddées avec le nouveau modèle renvoient des similarités aberrantes (ou des erreurs de dimension).

## Code concerné

```python
existing = await conn.fetchval(
    "SELECT content_hash FROM indexed_documents WHERE workspace_id=$1 AND path=$2", ...)
if existing == content_hash:
    files_skipped += 1
    continue
```

## Piste de correction

Inclure `indexer_used` dans la comparaison de skip (`existing == content_hash AND stored_indexer_used == job.indexer_used`), et/ou scoper la réutilisation de `chunk_hash` par modèle (stocker le modèle sur les lignes embeddings ou saler le hash avec `indexer_used`).
