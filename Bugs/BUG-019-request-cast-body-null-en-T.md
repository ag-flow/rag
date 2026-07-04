# BUG-019 — `request()` caste un body 2xx manquant/non-JSON en `T` : des null cachés derrière des types non-nullables

**Statut : 🔴 à corriger**

- **Zone** : frontend / lib/api
- **Sévérité** : basse
- **Complexité** : simple
- **Confiance** : faible (nécessite un upstream défaillant pour se déclencher ; le trou de typage, lui, est vérifié)
- **Fichiers** : `frontend/src/lib/api.ts:31-42`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — durcir le parsing hors 204/205

## Description

Sur toute réponse 2xx dont le body fait échouer `resp.json()` (body vide, HTML, JSON tronqué), `body` reste `null` et est retourné comme `T` — ex. `api.get<Workspace[]>` résout avec `null` typé `Workspace[]`. TypeScript autorise alors `data.map(...)` en aval, qui lève à l'exécution au lieu de faire remonter une erreur API propre.

## Scénario de défaillance

1. Un proxy mal configuré (ou le fallback Caddy `respond "ag-flow.rag — see /ui" 200` qui matche à cause d'une typo de path) renvoie 200 avec un body non-JSON.
2. `useWorkspaces()` résout avec succès avec `data === null` ; la table des workspaces fait `data.map` → `TypeError: Cannot read properties of null` — écran blanc React au lieu de l'état d'erreur de la query.

## Code concerné

```ts
let body: unknown = null;
try {
  body = await resp.json();
} catch {
  // 204 No Content ou réponse non-JSON
}
...
return body as T;
```

## Piste de correction

Pour les méthodes qui promettent un body, traiter un JSON 2xx imparsable comme une erreur (`ApiError` dédiée) sauf pour 204/205 ; ne garder le chemin tolérant que pour les réponses `void`.
