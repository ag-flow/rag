# BUG-025 — `GET /workspaces/{name}/apikey` renvoie la clé en fin de rotation après une rotation

**Statut : 🟢 corrigé**

- **Zone** : backend / api/admin
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `backend/src/rag/api/admin/__init__.py:138-150`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — ajuster l'ORDER BY / filtre

## Description

La requête conserve les clés en rotation pendant les 72 h de grâce (`rotated_at > now() - 72h`) et prend `ORDER BY created_at ASC LIMIT 1`. Après `POST .../api-keys/{id}/rotate` (qui insère une *nouvelle* ligne et estampille l'ancienne `rotated_at`), la plus ancienne ligne qui matche est l'ancienne clé en période de grâce.

## Scénario de défaillance

L'admin tourne la clé ; un conteneur redémarre et `init-rag.sh` appelle `GET /apikey` pour provisionner `.rag-client.json` → il reçoit l'ancienne clé, qui cesse silencieusement de fonctionner 72 h plus tard.

## Code concerné

```sql
AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
ORDER BY k.created_at ASC
LIMIT 1
```

## Piste de correction

Préférer les clés non tournées : `ORDER BY (rotated_at IS NOT NULL), created_at DESC` ou filtrer `rotated_at IS NULL` d'abord avec fallback.
