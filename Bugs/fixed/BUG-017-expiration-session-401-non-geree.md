# BUG-017 — Expiration de session non gérée en cours d'usage : les 401 post-login apparaissent comme des erreurs génériques, sans redirection

**Statut : 🟢 corrigé**

- **Zone** : frontend / lib/api + auth
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `frontend/src/lib/api.ts:25-43`, `frontend/src/hooks/useMe.ts:5-12`, `frontend/src/components/AuthGuard.tsx`, `frontend/src/main.tsx:12`
- **Modèle recommandé pour la correction** : **Opus** (`claude-opus-4-8`) — design transversal (handler global QueryCache/MutationCache, redirection, politique de retry)

## Description

La seule redirection 401 → login vit dans `AuthGuard`, indexée sur la query `useMe`. `useMe` a `staleTime: 5min`, `refetchOnWindowFocus: false` global, et `AuthGuard` ne réagit qu'au refetch. Rien dans `request()` ni dans un handler global QueryCache/MutationCache ne traite un 401 venant de n'importe quel autre endpoint comme « session expirée ». De plus, le `retry: 1` global (main.tsx:12) réessaie inutilement chaque 401/404 une fois avant d'échouer.

## Scénario de défaillance

1. Un admin laisse l'UI ouverte au-delà de la durée de vie du cookie de session, puis clique « save » sur un workspace ou ouvre l'onglet Sources.
2. L'API renvoie 401 ; React Query retente une fois, échoue, la page affiche un état d'erreur générique ou un toast.
3. L'utilisateur n'est jamais redirigé vers `/ui/login` et chaque action suivante échoue pareil jusqu'à un rechargement complet manuel.

## Code concerné

```ts
// api.ts — le 401 est levé comme n'importe quelle autre erreur, aucune gestion de session
if (!resp.ok) {
  throw new ApiError(resp.status, body);
}
```

## Piste de correction

Ajouter un handler global (`onError` de QueryCache/MutationCache, ou dans `request()`) qui sur `ApiError(401)` redirige vers `/ui/login?next=...` ; et/ou faire du `retry` par défaut une fonction qui saute les retries pour les 4xx.
