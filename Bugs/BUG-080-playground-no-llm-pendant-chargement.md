# BUG-080 — Playground chat affiche « no LLM configured » pendant que les configs chargent encore

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/workspace
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/PlaygroundChatTab.tsx:55-58,110-116`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Le résultat de `useLlmConfigs` défaute à `[]` ; `isLoading` n'est jamais consulté. Pendant le fetch, `enabledConfigs.length === 0` rend l'état vide « configure an LLM first ».

## Scénario de défaillance

Un utilisateur avec des LLM configurés ouvre l'onglet Playground sur une connexion lente → voit un flash « no LLM configured » (ou persistant tant que la requête pend), pouvant partir (re)configurer quelque chose qui existe déjà.

## Code concerné

```tsx
const { data: configs = [] } = useLlmConfigs(workspaceName);
...
if (enabledConfigs.length === 0) { return (<div ...>{t("chat.no_llm")}</div>); }
```

## Piste de correction

Renvoyer un spinner pendant `isLoading`.
