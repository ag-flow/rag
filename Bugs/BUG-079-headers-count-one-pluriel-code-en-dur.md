# BUG-079 — Compteur de headers webhook : clé plurielle `_one` codée en dur → la forme plurielle n'est jamais utilisée

**Statut : 🔴 à corriger**

- **Zone** : frontend / pages/workspace + i18n
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/WorkspaceWebhooksTab.tsx:103`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le code appelle `t("webhooks.headers_count_one", { count })`. Les fichiers i18n définissent `headers_count_one` et `headers_count_other` ; en nommant explicitement la clé `_one`, la résolution de pluriel d'i18next est contournée et la string singulière est toujours utilisée.

## Scénario de défaillance

Un webhook avec 3 headers affiche le libellé singulier (« 3 en-tête » au lieu de « 3 en-têtes »).

## Code concerné

```tsx
{t("webhooks.headers_count_one", { count: wh.headers.length })}
```

## Piste de correction

Appeler `t("webhooks.headers_count", { count })`.
