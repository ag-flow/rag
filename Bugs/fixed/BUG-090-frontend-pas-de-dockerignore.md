# BUG-090 — `frontend/Dockerfile` : pas de `.dockerignore` — `COPY . .` peut écraser `node_modules` installé par `npm ci`

**Statut : 🟢 corrigé**

- **Zone** : infra / frontend/Dockerfile
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/Dockerfile:8` (absence de `frontend/.dockerignore`)
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`backend/` a un `.dockerignore` (exclut `.venv/`), `frontend/` n'en a aucun. Le `COPY . .` après `npm ci` copie tout le contexte, y compris un `node_modules/` et un `dist/` locaux s'ils existent, écrasant les modules fraîchement installés dans l'image.

## Scénario de défaillance

Build lancé sur un poste où `npm install` a déjà tourné (dev local, ou LXC où on a débuggé le front à la main) : le `node_modules` hôte — potentiellement d'une autre plateforme (Windows) ou d'un lockfile antérieur — écrase celui de `npm ci` → `npm run build` échoue sur binaires natifs incompatibles, ou pire, builde avec des deps périmées sans erreur.

## Code concerné

```
COPY package*.json ./
RUN npm ci
COPY . .
```

## Piste de correction

Ajouter `frontend/.dockerignore` avec `node_modules/`, `dist/`.
