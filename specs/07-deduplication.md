# RAG Service — Déduplication par Hash

## Objectif

Éviter de consommer des crédits d'embedding sur des documents dont le contenu n'a pas changé. Chaque document indexé est associé à un hash SHA-256 de son contenu.

---

## Algorithme

```
document reçu (path + content)
        │
        ▼
hash = SHA-256(content)
        │
        ├── hash == indexed_documents[path].content_hash
        │         → status: "skipped" — 200 OK immédiat
        │
        └── hash != stocké (ou path inconnu)
                  │
                  ▼
            chunk le contenu
                  │
                  ▼
            embed via provider
                  │
                  ▼
            upsert dans pgvector
                  │
                  ▼
            update indexed_documents (hash + indexed_at)
                  │
                  ▼
            200 OK
```

---

## Cas couverts

| Situation | Comportement |
|---|---|
| Nouveau document | Indexation complète |
| Document inchangé | Skip — zéro appel embedding |
| Document modifié | Réindexation complète du document |
| Document supprimé (git) | Suppression des chunks dans pgvector |
| Changement d'indexeur | Invalidation de tous les hashes → réindexation forcée |

---

## Stockage du hash

Table `indexed_documents` dans la base `rag_config` :

```sql
(workspace_id, path) UNIQUE
content_hash          -- SHA-256 hex
indexer_used          -- "openai/text-embedding-3-small"
                      -- si l'indexeur change, le hash ne correspond plus
indexed_at
```

Le champ `indexer_used` permet de détecter une incohérence si l'indexeur d'un workspace est modifié — les anciens hashes sont alors invalides même si le contenu n'a pas changé.

---

## Comportement lors d'une sync git

Le sync worker récupère le diff git (fichiers ajoutés, modifiés, supprimés) :

```python
# Seuls les fichiers du diff sont traités
changed_files = git_diff(last_commit, current_commit)

for file in changed_files.modified + changed_files.added:
    content = read_file(file.path)
    hash = sha256(content)

    if get_stored_hash(workspace_id, file.path) == hash:
        increment_skipped()
        continue

    index_document(file.path, content, hash)
    increment_changed()

for file in changed_files.deleted:
    delete_chunks(workspace_id, file.path)
    delete_hash(workspace_id, file.path)
```

---

## Impact sur les jobs

Les jobs tracent les documents skippés pour visibilité :

```json
{
  "triggered_by": "webhook",
  "status": "done",
  "files_changed": 3,
  "files_skipped": 58,
  "duration_ms": 1240
}
```

Sur un vault de 61 fichiers avec 3 modifications — 58 appels embedding économisés.
