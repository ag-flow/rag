# rag-frontend

IHM web pour ag-flow.rag (M5b — page Workspaces).

## Quickstart dev

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173/ui (proxy /api+/auth+/me → backend LXC 303)
```

Env var optionnelle :
```bash
VITE_BACKEND_URL=http://localhost:8000 npm run dev
```

## Commandes

- `npm run dev` — Vite dev server avec hot reload
- `npm run build` — build prod dans `dist/`
- `npm run test` — Vitest watch mode
- `npm run test:run` — Vitest run once
- `npm run lint` — ESLint
- `npm run format` — Prettier
- `npm run typecheck` — TypeScript check sans emit

## Build prod

Le `Dockerfile` multi-stage build avec node 20 puis serve via Nginx alpine (cf. Dockerfile à la racine `frontend/`).
