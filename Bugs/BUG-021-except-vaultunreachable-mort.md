# BUG-021 — `except VaultUnreachable` mort : le resolver ne le lève jamais, une panne Harpocrate donne un 500 au lieu d'un 503

**Statut : 🟢 corrigé**

- **Zone** : backend / auth + api/admin + services/mcp
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/auth/workspace_auth.py:101-103`, `backend/src/rag/api/admin/__init__.py:160-163`, `backend/src/rag/services/mcp.py:114-117`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — capturer la bonne exception aux 3 sites

## Description

Ces sites appellent `resolver.resolve_with_retry(...)` et capturent `rag.api.errors.VaultUnreachable` pour mapper vers un 503 `harpocrate_unreachable`. Mais `SecretResolver` (`secrets/resolver.py`) ne lève que `VaultLookupFailed` (un `RuntimeError`), `UnknownAction`, `EnvVarMissing`, ou propage des erreurs de connexion SDK brutes. `VaultUnreachable` n'est levé que dans `services/workspaces.py`/`services/jobs.py`/`services/oidc.py` **après** qu'ils aient traduit `VaultLookupFailed`. Les clauses except ici ne peuvent jamais matcher.

## Scénario de défaillance

Harpocrate down + cache miss sur `/mcp` search, `GET /workspaces/{name}/apikey`, ou auth bearer workspace → `VaultLookupFailed`/`ConnectionError` se propage → 500 générique avec traceback au lieu du 503 prévu.

## Code concerné

```python
try:
    cached = await resolver.resolve_with_retry(api_key_ref)
except VaultUnreachable as e:          # jamais levé par le resolver
    raise HarpocrateUnreachableForApikey() from e
```

## Piste de correction

Capturer `VaultLookupFailed` (et les erreurs de connexion) à ces sites, ou faire lever `VaultUnreachable` par le resolver.
