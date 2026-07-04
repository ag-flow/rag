# BUG-074 — Playground chat : un `min_score` de 0 est impossible et saute silencieusement à 0.7 ; `top_k` idem

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/workspace
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/PlaygroundChatTab.tsx:143,155`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`parseFloat(e.target.value) || 0.7` traite `0` (et toute saisie partielle comme `"0."`) comme falsy et force 0.7 — ce qui est aussi incohérent avec le défaut d'état 0.3. `parseInt(...) || 5` pour top_k a le même défaut (impossible de vider le champ, « 0 » saute à 5).

## Scénario de défaillance

L'utilisateur veut un retrieval non filtré et tape `0` dans min score → la valeur devient instantanément 0.7, silencieusement *plus stricte* que le défaut ; l'utilisateur ne peut pas non plus taper « 0.05 » (le « 0 » intermédiaire reset à 0.7).

## Code concerné

```tsx
onChange={(e) => setMinScore(parseFloat(e.target.value) || 0.7)}
```

## Piste de correction

Garder la string brute en état et parser/clamper au blur ou à l'envoi ; utiliser des checks `Number.isNaN` au lieu de `||`.
