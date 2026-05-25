# M7b — Page Config OIDC admin (frontend + fix backend dépendance)

> **Statut** : design validé pour implémentation.
> **Prérequis** : M5a (backend OIDC), M5f (préfixe `/api/admin`), M7a (pattern page admin simple).

## 1. Contexte

Le backend M5a a livré `GET/POST /api/admin/oidc` (config singleton : issuer, client_id, client_secret_ref). Aujourd'hui, cette config s'édite uniquement via SQL ou curl avec master key — pas d'UI.

**Point critique découvert** : `backend/src/rag/api/admin_oidc.py` exige actuellement `require_master_key` seul, alors que toutes les autres routes admin acceptent **aussi** OIDC via `require_master_key_or_oidc_role("rag-admin")`. Conséquence : une UI accédée en mode normal (utilisateur authentifié via OIDC) reçoit 401 sur ces endpoints. M7b corrige cette incohérence.

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | **Form unique, pas de master-detail** | La config OIDC est un singleton (1 seule entrée en BDD) |
| D2 | **Mode upsert silencieux** : GET → 200 pré-remplit ; 404 → form vide en création | Même endpoint POST gère création et update côté backend |
| D3 | **Bouton Save désactivé si non-dirty** | Pattern cohérent M6 (édition api_key_ref) |
| D4 | **Bouton Annuler reset au dernier état serveur** | Standard form |
| D5 | **Fix backend : `require_master_key_or_oidc_role("rag-admin")`** | Sans ça l'UI est inutilisable. Pattern aligné avec les autres routes admin |
| D6 | **Pas de DELETE config** (reset) | Hors-scope M7b — peu de valeur, casse les sessions actives |
| D7 | **Pas de StatusIndicator sur la ref Harpocrate** | Demande backend extra (résolution effective). Hors-scope M7b |

## 3. Architecture backend (modif unique)

**`backend/src/rag/api/admin_oidc.py`** :

```python
# Avant
from rag.auth.bearer import require_master_key
# ...
dependencies=[Depends(require_master_key)],

# Après
from rag.auth.bearer import require_master_key_or_oidc_role
# ...
dependencies=[Depends(require_master_key_or_oidc_role("rag-admin"))],
```

**Tests à adapter** : `backend/tests/api/test_admin_oidc*.py` doivent vérifier que :
- 401 si ni master key ni session OIDC.
- 200/201 si master key Bearer.
- 200/201 si session OIDC avec rôle `rag-admin`.
- 403 si session OIDC mais rôle manquant.

## 4. Architecture frontend

### 4.1 Fichiers à créer

```
frontend/src/lib/oidc-config.types.ts          → OidcConfig, OidcConfigCreate
frontend/src/lib/oidc-config.ts                → oidcConfigApi (2 méthodes)
frontend/src/hooks/useOidcConfig.ts            → 1 query + 1 mutation
frontend/src/pages/OidcConfigPage.tsx          → form complet upsert
frontend/src/i18n/fr/oidc.json
frontend/src/i18n/en/oidc.json
frontend/src/pages/__tests__/OidcConfigPage.test.tsx
```

### 4.2 Fichiers à modifier

```
frontend/src/components/Sidebar.tsx            → +item "Config OIDC" sous Configuration
frontend/src/routes.tsx                        → +Route /settings/oidc-config
frontend/src/lib/i18n.ts                       → enregistrer namespace "oidc"
frontend/src/i18n/fr/nav.json                  → +clé items.oidc_config
frontend/src/i18n/en/nav.json                  → idem
```

### 4.3 Types TS

```typescript
// lib/oidc-config.types.ts
export type OidcConfig = {
  issuer: string;
  client_id: string;
  client_secret_ref: string;
};

export type OidcConfigCreate = {
  issuer: string;            // URL valide (validée Zod côté front + HttpUrl côté Pydantic)
  client_id: string;         // min 1, max 255
  client_secret_ref: string; // min 1, max 255
};
```

### 4.4 API client (`lib/oidc-config.ts`)

```typescript
const BASE = "/api/admin/oidc";

export const oidcConfigApi = {
  get: () => api.get<OidcConfig>(BASE),         // 404 si non configuré
  upsert: (payload: OidcConfigCreate) =>
    api.post<OidcConfig>(BASE, payload),
};
```

### 4.5 Hooks (`hooks/useOidcConfig.ts`)

- `useOidcConfig()` — query `["oidc-config"]`. Gestion 404 : `data = null` au lieu de throw (intercepter `ApiError` dans `queryFn`).
- `useUpsertOidcConfig()` — mutation, invalidate `["oidc-config"]`.

## 5. Layout UI

### 5.1 `OidcConfigPage.tsx`

```
┌──────────────────────────────────────────────────────────┐
│  Configuration OIDC                                       │
│  Authentification Single Sign-On (Keycloak, Auth0, …).   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │ Issuer URL                                       │    │
│  │ [https://keycloak.yoops.org/realms/yoops      ]  │    │
│  │                                                  │    │
│  │ Client ID                                        │    │
│  │ [rag                                          ]  │    │
│  │                                                  │    │
│  │ Référence client_secret (Harpocrate)             │    │
│  │ [keycloak_rag_client_secret                   ]  │    │
│  │                                                  │    │
│  │                              [Annuler] [Save]    │    │
│  └──────────────────────────────────────────────────┘    │
│                                                           │
│  ⚠ Modifier l'OIDC déconnecte les sessions actives.      │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Comportement

1. Mount → `GET /api/admin/oidc` :
   - 200 → form pré-rempli (`defaultValues` issus de `data`).
   - 404 (interceptée) → form vide en mode "première config".
2. Submit (`onValid`) → `POST` payload → toast succès + reset `dirty` (mais conserver valeurs).
3. Bouton Annuler : `form.reset(serverValues)` → revient au dernier état serveur.
4. Bouton Save désactivé si `!form.formState.isDirty || mutation.isPending`.
5. Bandeau warning amber en bas : "Modifier l'OIDC déconnecte les sessions actives."

### 5.3 Validation Zod

```typescript
const schema = z.object({
  issuer: z.string().url("invalid_url"),
  client_id: z.string().min(1, "required").max(255, "too_long"),
  client_secret_ref: z.string()
    .min(1, "required")
    .max(255, "too_long")
    .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only"),
});
```

## 6. Sidebar + Route

Dans `Sidebar.tsx`, section Configuration (juste après `Coffres Harpocrate`) :

```tsx
<NavItem
  to="/settings/oidc-config"
  icon={<KeyRound />}  // ou <ShieldCheck /> lucide-react
  label={t("items.oidc_config")}
/>
```

Dans `routes.tsx` :

```tsx
<Route path="/settings/oidc-config" element={<OidcConfigPage />} />
```

Clé i18n `nav.items.oidc_config` :
- FR : "Config OIDC"
- EN : "OIDC config"

## 7. i18n (namespace `oidc`)

Clés :

- `oidc.title` — "Configuration OIDC"
- `oidc.subtitle` — "Authentification Single Sign-On (Keycloak, Auth0, …)."
- `oidc.fields.issuer` — "Issuer URL"
- `oidc.fields.client_id` — "Client ID"
- `oidc.fields.client_secret_ref` — "Référence client_secret (Harpocrate)"
- `oidc.actions.cancel` — "Annuler"
- `oidc.actions.save` — "Enregistrer"
- `oidc.save.success` — "Configuration OIDC enregistrée."
- `oidc.save.error` — "Échec de l'enregistrement."
- `oidc.warning.sessions` — "Modifier l'OIDC déconnecte les sessions actives."
- `oidc.errors.invalid_url` — "URL invalide."
- `oidc.errors.required` — "Champ requis."
- `oidc.errors.too_long` — "Maximum 255 caractères."
- `oidc.errors.alphanum_underscore_only` — "Caractères autorisés : a-z, A-Z, 0-9, underscore."

## 8. Tests Vitest

1 fichier : `OidcConfigPage.test.tsx` :

- Render avec config existante (mock `useOidcConfig` retourne data) → form pré-rempli.
- Render sans config (mock retourne `null`) → form vide.
- Save désactivé tant que non-dirty.
- Submit avec valeurs valides → mutation appelée avec le payload correct.
- Erreur URL invalide affichée si issuer ne match pas une URL.

## 9. Plan d'attaque

1. **T1** — Backend fix dépendance + tests
2. **T2** — Types TS + API client + hooks
3. **T3** — Sidebar +item + route + `OidcConfigPage` squelette
4. **T4** — Form complet (Zod + GET/POST + Save/Cancel + warning bandeau)
5. **T5** — i18n FR+EN + test Vitest + audit strings

Estimation : 5 tâches, ~demi-journée.
