# BUG-061 — Le cache JWKS OIDC n'a ni TTL ni invalidation sur échec de signature

**Statut : 🔴 à corriger**

- **Zone** : backend / services/oidc
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/services/oidc.py:180-203,221-226`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`_jwks` cache le keyset pour toujours ; la docstring prétend « Reload on signature fail handled by caller », mais `verify_id_token` lève `OidcInvalidToken("bad_signature")` sans jamais évincer `_jwks_cache`. Le discovery est TTL'd (1 h) mais pas le JWKS.

## Scénario de défaillance

Keycloak tourne ses clés de signature → chaque login/refresh échoue en `bad_signature` jusqu'au redémarrage du process backend.

## Code concerné

```python
cached = self._jwks_cache.get(discovery.jwks_uri)
if cached is not None:
    return cached          # jamais rafraîchi, jamais invalidé
```

## Piste de correction

Sur `BadSignatureError`, évincer `self._jwks_cache[jwks_uri]` et retenter une fois ; ou TTL le cache JWKS comme le discovery.
