# BUG-054 — Les secrets de headers webhook avec `vault` ne sont jamais écrits dans Harpocrate → valeur silencieusement perdue, ref pendante stockée

**Statut : 🔴 à corriger**

- **Zone** : backend / services/webhooks
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/services/webhooks.py:164-178` (create), `296-302` (patch)
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — écriture vault + branche update, cohérence avec `source_webhooks`

## Description

`_resolve_header_write` construit une ref vault fraîche (`/workspaces/{ws}/hooks/{wh_id}/headers/{name}` — le path inclut le `wh_id` tout juste créé, donc ne peut pas préexister) et renvoie `value_in_db=None`, mais **aucun `set_secret` n'est jamais appelé** (le param `resolver` de `create_webhook` est totalement inutilisé). De même, `patch_webhook_header` sur un header vault-backed ne fait que `log.info(...)` et jette la nouvelle valeur.

## Scénario de défaillance

L'admin crée un webhook avec un header `Authorization` stocké « en vault ». La valeur du header est perdue ; au dispatch, `resolve_with_retry(vault_ref)` échoue (secret introuvable), le header est sauté avec juste un warning log, et chaque appel webhook part non authentifié → le récepteur rejette en 401 et l'admin n'a aucune erreur au moment de la config.

## Code concerné

```python
if vault and value:
    logical = f"/workspaces/{workspace_name}/hooks/{wh_id}/headers/{header_name}"
    vault_ref = build_ref(vault, logical)
    return vault_ref, None        # valeur jamais persistée
```

## Piste de correction

Dans `_resolve_header_write`, écrire le secret via le service/client vault (comme `source_webhooks.enable_webhook`) avant de renvoyer la ref ; implémenter la branche update vault dans `patch_webhook_header`.
