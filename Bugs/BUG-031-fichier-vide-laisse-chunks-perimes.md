# BUG-031 — Fichier vidé dans git : chunks périmés conservés dans le vector store et réindexé à l'infini

**Statut : 🔴 à corriger**

- **Zone** : backend / indexer
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/indexer/real.py:118-122` (+ `:148-149` legacy, `:203-204` structured)
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Quand le nouveau contenu d'un fichier déjà indexé produit 0 chunk (fichier tronqué à vide/whitespace, ou réduit à rien par `CleaningChunkerWrapper`), `index_file` renvoie 0 **avant** de toucher la base workspace et **avant** `_record_indexed_document`. Les anciens chunks de ce path ne sont jamais supprimés (la branche delete-on-empty de `upsert_chunks` est inatteignable car `_index_legacy` retourne à `if not chunks: return 0`), et `indexed_documents.content_hash` garde l'ancien hash.

## Scénario de défaillance

Un repo commit `docs/a.md` → indexé. Commit suivant vide `docs/a.md`. À chaque sync : hash différent → `index_file` appelé → 0 chunk → rien supprimé, hash non enregistré. Les chunks périmés de l'ancien contenu restent cherchables indéfiniment, et le fichier est retraité inutilement à chaque sync.

## Code concerné

```python
if n_chunks == 0:
    log.info("real_indexer.empty_content_skipped", path=path)
    return 0
await self._record_indexed_document(workspace_id, path, content_hash, indexer_used, title)
```

## Piste de correction

Sur 0 chunk pour un document existant, supprimer les chunks/sections du path et enregistrer quand même le nouveau content_hash (ou supprimer la ligne `indexed_documents`).
