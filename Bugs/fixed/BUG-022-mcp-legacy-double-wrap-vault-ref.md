# BUG-022 — `/mcp` legacy double-wrappe les refs vault complètes → `UnknownAction` → 500

**Statut : 🟢 corrigé**

- **Zone** : backend / services/mcp
- **Sévérité** : haute
- **Complexité** : simple (mais lié au BUG-025, corriger ensemble via helper partagé)
- **Fichiers** : `backend/src/rag/services/mcp.py:302-306,352-356`, endpoint `backend/src/rag/api/mcp.py:19`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — refléter `RealIndexer._resolve_api_key` (voir note transversale BUG-025)

## Description

`_search_one` wrappe inconditionnellement `indexer_configs.api_key_ref` avec `_to_vault_ref(ctx["api_key_ref"], default_vault_name)`, supposant une *clé logique*. Mais selon `IndexerCreateSpec` (« api_key_ref est le harpo_path d'une provider_api_key existante ») et `services/provider_api_keys._build_vault_ref`, la valeur stockée est déjà une ref complète `${vault://<name>:/provider/key}`. Le wrapping produit `${vault://X:${vault://...}}` ; le `_VAULT_RE` du resolver échoue sur le `}` imbriqué et `_GENERIC_RE` matche → `raise UnknownAction`. À noter : `RealIndexer._resolve_api_key` (`indexer/real.py:263-276`) gère les deux formes via un check `is_vault_ref` — pas ce site. Même défaut pour la ref rerank ligne 352.

## Scénario de défaillance

Workspace créé via le flux UI actuel (api_key_ref en ref complète) → `POST /mcp` search → `UnknownAction("Unknown declarative action: 'vault'")` → 500 pour chaque recherche sur ce workspace.

## Code concerné

```python
if ctx["api_key_ref"]:
    api_key = await secret_resolver.resolve_with_retry(
        _to_vault_ref(ctx["api_key_ref"], default_vault_name)  # double-wrappe les refs complètes
    )
```

## Piste de correction

Refléter `RealIndexer._resolve_api_key` : ne wrapper que si `not is_vault_ref(ref)`. Voir BUG-025 (helper partagé pour les 4 sites d'appel).
