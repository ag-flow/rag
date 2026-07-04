# BUG-016 — `useJobLogs` ne gère jamais la fermeture du WebSocket : statut de job bloqué sur « running » à jamais

**Statut : 🔴 à corriger**

- **Zone** : frontend / hooks
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/hooks/useJobLogs.ts:28-39`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — onclose + try/catch, localisé

## Description

Le hook passe `jobStatus` à `"done"`/`"error"` uniquement à l'arrivée d'une frame `{type:"done"}`, et `"error"` sur `onerror`. Il n'y a pas de handler `onclose`. Une fermeture propre côté serveur (redémarrage backend, deploy, timeout idle Caddy/proxy, changement de réseau) déclenche `onclose` sans `onerror` et sans frame `done`. De plus, `JSON.parse(e.data)` n'est pas protégé — une frame malformée/non-JSON lève une exception non capturée dans le handler.

## Scénario de défaillance

1. L'utilisateur lance un réindex et regarde les logs live ; le backend redémarre (ou le proxy WS timeout) en cours de job.
2. Le socket se ferme proprement, aucun événement `done` reçu → le spinner UI affiche « running » indéfiniment, sans erreur, même après que le job a réellement fini côté serveur.

## Code concerné

```ts
ws.onmessage = (e: MessageEvent) => {
  const event: WsEvent = JSON.parse(e.data as string);  // non protégé
  ...
};
ws.onerror = () => setJobStatus("error");
return () => ws.close();   // pas de ws.onclose → "running" pour toujours
```

## Piste de correction

Ajouter `ws.onclose` qui bascule un statut encore `running` vers `"error"` (ou déclenche un poll REST de repli du statut du job) ; envelopper `JSON.parse` dans un try/catch.
