# BUG-009 — `SourceUpdateRequest` sans le validateur `config.url` : un PATCH peut effacer l'URL git

**Statut : 🟢 corrigé**

- **Zone** : backend / schemas + services/sources
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/schemas/admin.py:129-139` (vs validateur en 118-124), `backend/src/rag/services/sources.py:206`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — copier le validateur existant ou merger la config

## Description

`SourceCreateRequest` impose `config.url` via `config_must_have_url`. `SourceUpdateRequest` déclare le même champ requis `config: dict[str, Any]` mais **sans** le validateur, et `update_source` remplace la config stockée en bloc (`config = dict(request.config)` — seuls les cinq champs d'auth sont préservés de la config courante, `url` ne l'est pas).

## Scénario de défaillance

1. `PATCH /workspaces/x/sources/{id}` avec `{"config": {"branch": "main"}}` (client mettant à jour uniquement la branche, ignorant que config = remplacement, pas merge).
2. Validation OK → source persistée sans `url` → le prochain sync planifié échoue au clone/pull git à chaque cycle avec une erreur confuse ; la mauvaise config a été acceptée avec un 200.

## Code concerné

```python
class SourceUpdateRequest(BaseModel):
    ...
    config: dict[str, Any]   # pas de validateur url, contrairement à SourceCreateRequest
```

## Piste de correction

Ajouter le même `field_validator` `config_must_have_url` à `SourceUpdateRequest` (ou merger les configs dans le service).
