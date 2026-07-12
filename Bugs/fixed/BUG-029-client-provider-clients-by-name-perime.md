# BUG-029 — `HarpocrateClientProvider._load` laisse `_clients_by_name` périmé quand la table vault se vide

**Statut : 🟢 corrigé**

- **Zone** : backend / secrets
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/secrets/client_provider.py:79-83`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — une ligne à ajouter

## Description

La branche table-vide réinitialise `_clients` et `_default_name` mais pas `_clients_by_name`. Les lookups par nom (`${vault://<vault_name>:...}` refs venant de provider_api_keys/git_credentials/ssh_keys) continuent de résoudre contre les clients de vaults supprimés pour toute la durée de vie du process.

## Scénario de défaillance

L'admin supprime le dernier vault (ex. pour tourner un token Harpocrate compromis) → le TTL du cache expire → `_load` voit la table vide → les lookups par nom renvoient toujours l'ancien client avec le token révoqué, produisant des 401 confus de Harpocrate au lieu de `VaultNotFoundError` ; ou pire, continue d'utiliser un token censé être décommissionné.

## Code concerné

```python
if not vaults:
    self._clients = {}
    self._default_name = None      # _clients_by_name PAS vidé
    log.info("vault.load.empty", ...)
    return
```

## Piste de correction

Vider aussi `self._clients_by_name = {}` dans la branche vide.
