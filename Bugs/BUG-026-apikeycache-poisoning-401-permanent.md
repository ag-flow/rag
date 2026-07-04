# BUG-026 — Empoisonnement de l'`ApiKeyCache` : sur mismatch du clair, l'entrée périmée n'est jamais invalidée → 401 permanent jusqu'au restart

**Statut : 🟢 corrigé**

- **Zone** : backend / auth + api/mcp_standard + services/mcp
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/auth/workspace_auth.py:95-112`, `backend/src/rag/api/mcp_standard.py:436-443`, `backend/src/rag/services/mcp.py:111-124`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — invalider + re-résoudre sur mismatch

## Description

`ApiKeyCache` a la durée de vie du process, sans TTL. Quand le fingerprint matche en DB mais que le clair caché sous le même `api_key_ref` ne matche pas (`compare_digest` échoue — le commentaire du code nomme lui-même le scénario de rotation out-of-band), le code renvoie 401 sans invalider le cache ni re-résoudre. L'entrée périmée rejette alors la clé valide à chaque requête suivante, pour toujours.

## Scénario de défaillance

Valeur du secret changée dans Harpocrate au même path + fingerprint mis à jour en DB (rotation out-of-band, restore, ou fix manuel) → chaque requête avec la nouvelle clé correcte : fingerprint matche, cache sert l'ancien clair, mismatch → 401 jusqu'au redémarrage du process.

## Code concerné

```python
if not compare_digest(cached, api_key):
    # Très rare : fingerprint matché mais clair non. ...
    raise HTTPException(status_code=401, detail="invalid_workspace_apikey")
```

## Piste de correction

Sur mismatch, `cache.invalidate(ref)` et re-résoudre une fois avant de renvoyer 401.
