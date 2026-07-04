# BUG-087 — `smoke-m5e.sh` complètement obsolète : variable env inexistante + INSERT sur des colonnes supprimées

**Statut : 🟢 corrigé**

> Résolution : script `scripts/smoke-m5e.sh` **supprimé** (`git rm`). Il n'était
> référencé nulle part hors sa fiche et l'index `Bugs/README.md`. Le réécrire
> aurait imposé de reconstituer tout le flux `workspace_api_keys` + Harpocrate
> (le bypass par INSERT SQL direct n'est plus possible : colonnes
> `api_key_encrypted`/`api_key_fingerprint` droppées par migrations 015/033) ;
> la suppression est donc l'option propre.

- **Zone** : infra / scripts
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `scripts/smoke-m5e.sh:13,20`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — réécriture contre le modèle actuel ou suppression (décision)

## Description

Double rupture vérifiée : (1) `RAG_API_KEY_DEK` n'existe ni dans `backend/src/rag/config.py`, ni dans aucun `.env.example` → le script sort toujours en « RAG_API_KEY_DEK vide ». (2) L'INSERT cible `workspaces(api_key_encrypted, api_key_fingerprint, …)` : `api_key_encrypted` a été droppée par `migrations/015_workspaces_apikey_ref.sql:10` et `api_key_fingerprint` par `033_workspace_api_keys.sql:18`. Le GET `/apikey` actuel lit `workspace_api_keys` + Harpocrate, plus du tout `pgp_sym_decrypt` sur `workspaces`.

## Scénario de défaillance

Quiconque relance ce smoke pour valider un déploiement obtient un échec immédiat (`ON_ERROR_STOP` sur colonne inexistante) et peut conclure à tort que le déploiement est cassé.

## Code concerné

```
DEK=$(grep ^RAG_API_KEY_DEK= "$ENV_FILE" | cut -d= -f2-)
...
SQL_INSERT="INSERT INTO workspaces (name, api_key_encrypted, api_key_fingerprint, rag_cnx, rag_base) VALUES (...)"
```

## Piste de correction

Supprimer le script ou le réécrire contre le modèle `workspace_api_keys`/Harpocrate.
