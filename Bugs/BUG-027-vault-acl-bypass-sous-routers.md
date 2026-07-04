# BUG-027 — Contournement de l'ACL owner des vaults via les sous-routers (ssh-keys / git-credentials / provider-keys)

**Statut : 🔴 à corriger**

- **Zone** : backend / api (sous-routers harpocrate)
- **Sévérité** : moyenne (sécurité — élévation horizontale entre owners)
- **Complexité** : modérée
- **Fichiers** : `backend/src/rag/api/admin_ssh_keys.py:38-101`, `backend/src/rag/api/admin_git_credentials.py:44-113`, `backend/src/rag/api/admin_provider_keys.py:63-132`
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — sécurité, multi-fichiers, cohérence ACL

## Description

`admin_harpocrate_vaults.py` impose `_check_vault_access` (match owner pour les écritures, owner-ou-défaut pour les lectures) sur chaque endpoint vault. Les routers imbriqués sous `/api/admin/harpocrate-vaults/{vault_id}/...` récupèrent le vault via `svc.get_by_id` mais n'appellent **jamais** `_check_vault_access` — aucun contrôle d'owner.

## Scénario de défaillance

L'utilisateur OIDC A (rag-admin) connaît/énumère le vault_id du vault privé de l'utilisateur B (non listé pour A, mais les ids fuitent dans les logs/UI d'écrans partagés) : A peut lister les clés SSH de B, créer/supprimer des clés provider et des credentials git dans le vault de B, et supprimer les clés SSH de B — opérations que l'ACL au niveau vault interdit explicitement (même `GET /{vault_id}` renvoie 403 pour A).

## Code concerné

```python
vault = await svc.get_by_id(conn, vault_id)
if vault is None:
    raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
# pas de check owner — procède au delete/import dans le vault de n'importe quel owner
```

## Piste de correction

Appeler `_check_vault_access(vault, get_current_owner_id(request), write=...)` dans chaque handler imbriqué (read pour GET, write pour POST/PATCH/DELETE).
