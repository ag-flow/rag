# BUG-062 — `reindex_workspace` : omettre `api_key_ref` dans un spec indexeur par ailleurs identique déclenche le drop/recreate destructif et nulle la ref stockée

**Statut : 🟢 corrigé**

- **Zone** : backend / services/jobs
- **Sévérité** : moyenne
- **Complexité** : simple
- **Confiance** : moyenne
- **Fichiers** : `backend/src/rag/services/jobs.py:226-230,275-286`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`same_indexer` compare aussi `api_key_ref`. Une requête avec les mêmes provider/model mais `api_key_ref=None` (champ omis) est classée comme *changement* d'indexeur : table droppée, `indexed_documents` effacé, et `UPDATE indexer_configs SET ... api_key_ref=$3` écrit `NULL`, effaçant la ref de clé configurée.

## Scénario de défaillance

Le client renvoie le spec indexeur sans le champ clé optionnel + `confirm=true` (croyant à un simple reindex) → destruction complète de l'index *et* le workspace perd sa ref de clé API d'embedding → les indexations suivantes échouent à l'auth.

## Code concerné

```python
same_indexer = new_indexer is None or (
    new_indexer.provider == row["provider"]
    and new_indexer.model == row["model"]
    and (new_indexer.api_key_ref or None) == (row["api_key_ref"] or None)
)
```

## Piste de correction

Traiter `api_key_ref=None` comme « inchangé » (sémantique `COALESCE`), ou ne comparer que provider/model pour la décision destructive.
