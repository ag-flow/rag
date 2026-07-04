# BUG-069 — Les actions webhook passent l'UUID de source comme `source_name` quand `source.name` est null

**Statut : 🔴 à corriger**

- **Zone** : frontend / pages/workspace
- **Sévérité** : haute
- **Complexité** : modérée
- **Fichiers** : `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx:137,144,149`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — décision front/back (accepter id-ou-nom ou désactiver l'action)

## Description

Les actions du menu webhook utilisent `source.name ?? source.id`. `Source.name` est typé `string | null` (`lib/workspaces.types.ts`), et le backend résout les routes webhook strictement par nom (`WHERE w.name = $1 AND ws.name = $2` dans `backend/src/rag/services/source_webhooks.py`). Un UUID ne matchera jamais `ws.name`.

## Scénario de défaillance

Sur une source legacy avec `name = null`, cliquer « Enable webhook » envoie `POST .../sources/<uuid>/webhook/enable` → backend `ValueError: Source '<uuid>' not found` → l'utilisateur ne voit qu'un toast d'erreur générique ; feature inutilisable pour cette source.

## Code concerné

```tsx
onSelect={() => setWebhookEnableTarget(source.name ?? source.id)}
```

## Piste de correction

Désactiver les actions webhook pour les sources sans nom (avec un hint), ou faire accepter id-ou-nom par le backend.
