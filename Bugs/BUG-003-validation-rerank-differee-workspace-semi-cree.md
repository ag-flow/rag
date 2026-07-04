# BUG-003 — Validation du rerank différée après création du workspace : provider invalide = workspace semi-créé sans clé API

**Statut : 🟢 corrigé**

- **Zone** : backend / schemas + services/workspaces
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/schemas/admin.py:42-53` (`RerankCreateSpec`), `backend/src/rag/services/workspaces.py:163-186`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — ajout de Literal + éventuelle compensation, localisé

## Description

`RerankCreateSpec.provider` est un simple `str` (pas de Literal), donc `POST /workspaces` accepte n'importe quelle chaîne. Le service construit le `RerankSpec` (qui a le Literal) seulement **après** la création des lignes de config, de la base physique `rag_<name>` et des migrations workspace. Un provider invalide lève une `ValidationError` pydantic depuis le service — pas une `RequestValidationError` — donc le client reçoit un 500. L'étape 5 (création de la clé API) n'est jamais exécutée, et il n'y a aucune compensation (contrairement à l'étape DDL qui, elle, rollback).

## Scénario de défaillance

1. `POST /workspaces {"name":"x", "indexer":{...}, "rerank":{"provider":"cohre",...}}` (typo).
2. Ligne workspace, indexer_config, chunking_config et base `rag_x` créées → `RerankSpec(provider="cohre")` lève → 500, aucune `api_key` délivrée.
3. Re-tenter le POST → `WorkspaceAlreadyExists` (409). Workspace inutilisable, suppression manuelle obligatoire.

## Code concerné

```python
class RerankCreateSpec(BaseModel):
    provider: str = Field(min_length=1)   # pas de Literal
...
# workspaces.py:172 — après succès du DDL, peut lever ValidationError :
rerank_spec = RerankSpec(provider=request.rerank.provider, ...)
```

## Piste de correction

Donner à `RerankCreateSpec.provider` le même Literal (validation au parsing de la requête → 422 avant tout effet de bord), et/ou ajouter une compensation autour de l'étape rerank comme pour l'étape DDL.
