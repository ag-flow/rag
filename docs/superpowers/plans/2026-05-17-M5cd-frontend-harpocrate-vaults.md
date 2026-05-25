# M5cd-frontend — Page Settings UI Coffres Harpocrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter la page Settings UI permettant à l'admin RAG de gérer les coffres Harpocrate sans toucher au `.env` ni à curl. Master-detail + 3 onglets internes (Détail / Secrets / Info wallet) + 4 dialogs (Create / ReplaceApiKey / Reveal / Retire).

**Architecture:** React 18 + TypeScript strict + react-router-dom + TanStack Query + Tailwind + shadcn/ui + i18next (déjà installés en M5b). Consomme les 12 endpoints backend M5c + M5d. Sélection courante synchronisée avec `?vault=<id>` (URLSearchParams). Hooks React Query avec lazy loading sur les tabs Secrets/Info (enabled controlled).

**Tech Stack:** Frontend stack M5b (cf. spec design `docs/superpowers/specs/2026-05-17-M5cd-frontend-harpocrate-vaults-design.md`). Backend déjà déployé : M5c (`m5c-backend-done`) + M5d (`m5d-backend-done`).

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `frontend/src/lib/harpocrate-vaults.types.ts` | **Create** | 9 types TS miroirs des schemas Pydantic backend |
| `frontend/src/lib/harpocrate-vaults.ts` | **Create** | 12 méthodes API client (CRUD + M5d) |
| `frontend/src/hooks/useHarpocrateVaults.ts` | **Create** | 4 queries + 6 mutations React Query |
| `frontend/src/components/Sidebar.tsx` | **Modify** | +section Configuration +item Coffres Harpocrate |
| `frontend/src/routes.tsx` | **Modify** | +route `/settings/harpocrate-vaults` |
| `frontend/src/pages/HarpocrateVaultsPage.tsx` | **Create** | Container master-detail + state sélection URL-synced |
| `frontend/src/pages/harpocrate/VaultsList.tsx` | **Create** | Liste 240px + bouton +Nouveau + état vide (warning DEK) |
| `frontend/src/pages/harpocrate/VaultDetailPanel.tsx` | **Create** | Panneau droit max 760px : header + tabs container |
| `frontend/src/pages/harpocrate/VaultDetailTab.tsx` | **Create** | Onglet Détail (formulaire édition + save) |
| `frontend/src/pages/harpocrate/VaultSecretsTab.tsx` | **Create** | Onglet Secrets (filtres + table + copy) |
| `frontend/src/pages/harpocrate/VaultWalletInfoTab.tsx` | **Create** | Onglet Info wallet (sections lecture seule) |
| `frontend/src/pages/harpocrate/CreateVaultDialog.tsx` | **Create** | Modal création |
| `frontend/src/pages/harpocrate/ReplaceApiKeyDialog.tsx` | **Create** | Modal remplacement token |
| `frontend/src/pages/harpocrate/RevealApiKeyDialog.tsx` | **Create** | Modal confirmation + display masqué |
| `frontend/src/pages/harpocrate/RetireVaultDialog.tsx` | **Create** | Modal avec input confirmation nom |
| `frontend/src/i18n/fr/harpocrate.json` | **Create** | Tous labels FR |
| `frontend/src/i18n/en/harpocrate.json` | **Create** | Tous labels EN |
| `frontend/src/i18n/i18n.ts` | **Modify** | Enregistrer namespace `harpocrate` |
| `frontend/src/pages/harpocrate/__tests__/*.test.tsx` | **Create** | Tests Vitest (~6 fichiers) |

---

## Task 1: Lib API client + types TypeScript

**Files:**
- Create: `frontend/src/lib/harpocrate-vaults.types.ts`
- Create: `frontend/src/lib/harpocrate-vaults.ts`

**Contexte** : `lib/api.ts` existe déjà (M5b) avec `api.get/post/put/patch/delete` + `ApiError`. On l'utilise. Pattern à suivre : cf. `lib/api.ts` (déjà installé).

- [ ] **Step 1: Créer `lib/harpocrate-vaults.types.ts`**

Tous les types TS miroirs des schemas Pydantic backend (cf. spec §4.3). 9 types : `VaultSummary`, `VaultCreateRequest`, `VaultUpdateRequest`, `VaultRotateApiKeyRequest`, `VaultTestConnectionResult`, `VaultRevealApiKeyResponse`, `WalletInfoResponse`, `SecretTypeSummary`, `SecretListItem`, `SecretListResponse`.

- [ ] **Step 2: Créer `lib/harpocrate-vaults.ts` avec 12 méthodes**

```typescript
import { api } from "@/lib/api";
import type {
  SecretListResponse,
  SecretTypeSummary,
  VaultCreateRequest,
  VaultRevealApiKeyResponse,
  VaultRotateApiKeyRequest,
  VaultSummary,
  VaultTestConnectionResult,
  VaultUpdateRequest,
  WalletInfoResponse,
} from "@/lib/harpocrate-vaults.types";

const BASE = "/api/admin/harpocrate-vaults";

export const harpocrateVaultsApi = {
  list: () => api.get<VaultSummary[]>(BASE),
  get: (id: string) => api.get<VaultSummary>(`${BASE}/${id}`),
  create: (payload: VaultCreateRequest) => api.post<VaultSummary>(BASE, payload),
  update: (id: string, payload: VaultUpdateRequest) =>
    api.patch<VaultSummary>(`${BASE}/${id}`, payload),
  delete: (id: string) => api.delete<void>(`${BASE}/${id}`),
  replaceApiKey: (id: string, payload: VaultRotateApiKeyRequest) =>
    api.post<VaultSummary>(`${BASE}/${id}/rotate-api-key`, payload),
  setDefault: (id: string) => api.post<VaultSummary>(`${BASE}/${id}/set-default`, {}),
  testConnection: (id: string) =>
    api.post<VaultTestConnectionResult>(`${BASE}/${id}/test-connection`, {}),
  revealApiKey: (id: string) => api.get<VaultRevealApiKeyResponse>(`${BASE}/${id}/api-key`),
  getWalletInfo: (id: string) => api.get<WalletInfoResponse>(`${BASE}/${id}/info`),
  listTypes: (id: string, params: { q?: string; include_deprecated?: boolean } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.include_deprecated) qs.set("include_deprecated", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<SecretTypeSummary[]>(`${BASE}/${id}/types${suffix}`);
  },
  listSecrets: (
    id: string,
    params: { path?: string; name_contains?: string; tag?: string; limit?: number } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.path) qs.set("path", params.path);
    if (params.name_contains) qs.set("name_contains", params.name_contains);
    if (params.tag) qs.set("tag", params.tag);
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<SecretListResponse>(`${BASE}/${id}/secrets${suffix}`);
  },
};
```

- [ ] **Step 3: Smoke TypeScript**

```powershell
cd frontend
npx tsc --noEmit
```

Expected : clean.

- [ ] **Step 4: Lint**

```powershell
npm run lint
```

Expected : clean.

- [ ] **Step 5: Commit**

```powershell
cd ..
git add frontend/src/lib/harpocrate-vaults.types.ts frontend/src/lib/harpocrate-vaults.ts
git commit -m "feat(M5cd-front): API client + types Harpocrate vaults (12 méthodes)"
```

---

## Task 2: Hooks React Query

**Files:**
- Create: `frontend/src/hooks/useHarpocrateVaults.ts`

**Contexte** : pattern `useWorkspaces.ts` existant (queryClient.invalidateQueries après mutation).

- [ ] **Step 1: Créer le fichier de hooks**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { harpocrateVaultsApi } from "@/lib/harpocrate-vaults";
import type {
  VaultCreateRequest,
  VaultRotateApiKeyRequest,
  VaultUpdateRequest,
} from "@/lib/harpocrate-vaults.types";

const ROOT_KEY = ["vaults"] as const;

// ─── Queries ─────────────────────────────────────────

export function useVaults() {
  return useQuery({
    queryKey: ROOT_KEY,
    queryFn: harpocrateVaultsApi.list,
    staleTime: 30_000,
  });
}

export function useVault(id: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, id],
    queryFn: () => harpocrateVaultsApi.get(id!),
    enabled: !!id,
    staleTime: 30_000,
  });
}

export function useVaultWalletInfo(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: [...ROOT_KEY, id, "info"],
    queryFn: () => harpocrateVaultsApi.getWalletInfo(id!),
    enabled: !!id && enabled,
    staleTime: 30_000,
  });
}

export function useVaultSecrets(
  id: string | null,
  filters: { path?: string; name_contains?: string; tag?: string; limit?: number },
  enabled: boolean,
) {
  return useQuery({
    queryKey: [...ROOT_KEY, id, "secrets", filters],
    queryFn: () => harpocrateVaultsApi.listSecrets(id!, filters),
    enabled: !!id && enabled,
    staleTime: 30_000,
  });
}

// ─── Mutations ───────────────────────────────────────

export function useCreateVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VaultCreateRequest) => harpocrateVaultsApi.create(payload),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ROOT_KEY }); },
  });
}

export function useUpdateVault(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VaultUpdateRequest) => harpocrateVaultsApi.update(id, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ROOT_KEY });
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, id] });
    },
  });
}

export function useDeleteVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => harpocrateVaultsApi.delete(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ROOT_KEY }); },
  });
}

export function useReplaceApiKey(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: VaultRotateApiKeyRequest) =>
      harpocrateVaultsApi.replaceApiKey(id, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, id] });
      // Invalide aussi info wallet (api_key_id changé)
      void qc.invalidateQueries({ queryKey: [...ROOT_KEY, id, "info"] });
    },
  });
}

export function useSetDefaultVault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => harpocrateVaultsApi.setDefault(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ROOT_KEY }); },
  });
}

export function useTestConnection(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => harpocrateVaultsApi.testConnection(id),
    onSuccess: (result) => {
      // Stocke localement le dernier test pour le badge header
      qc.setQueryData([...ROOT_KEY, id, "lastTest"], result);
    },
  });
}

export function useLastTestResult(id: string | null) {
  const qc = useQueryClient();
  if (!id) return null;
  return qc.getQueryData<{ ok: boolean; detail: string; probe_path_used: string }>([
    ...ROOT_KEY, id, "lastTest",
  ]);
}

export function useRevealApiKey(id: string) {
  return useMutation({
    mutationFn: () => harpocrateVaultsApi.revealApiKey(id),
    // pas de cache : chaque appel = audit log côté backend
  });
}
```

- [ ] **Step 2: Smoke tsc + lint**

```powershell
cd frontend
npx tsc --noEmit && npm run lint
```

- [ ] **Step 3: Commit**

```powershell
cd ..
git add frontend/src/hooks/useHarpocrateVaults.ts
git commit -m "feat(M5cd-front): hooks React Query Harpocrate vaults (4 queries + 6 mutations)"
```

---

## Task 3: Sidebar +section Configuration + route + page squelette

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/routes.tsx`
- Create: `frontend/src/pages/HarpocrateVaultsPage.tsx`
- Modify: `frontend/src/i18n/fr/nav.json`
- Modify: `frontend/src/i18n/en/nav.json`

- [ ] **Step 1: Ajouter section Configuration au Sidebar**

Après la section "Usage" dans `Sidebar.tsx`, ajouter :

```tsx
import { Settings } from "lucide-react";
// ...
<div className="px-5 pt-4 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
  {t("sections.configuration")}
</div>
<NavItem
  to="/settings/harpocrate-vaults"
  icon={<Settings />}
  label={t("items.harpocrate_vaults")}
/>
```

- [ ] **Step 2: Mettre à jour i18n nav**

`frontend/src/i18n/fr/nav.json` : ajouter
```json
{
  "sections": { "configuration": "Configuration" },
  "items": { "harpocrate_vaults": "Coffres Harpocrate" }
}
```

Idem en anglais (`Configuration` / `Harpocrate vaults`).

- [ ] **Step 3: Ajouter la route**

`routes.tsx` :
```tsx
import { HarpocrateVaultsPage } from "@/pages/HarpocrateVaultsPage";
// ...
<Route path="/settings/harpocrate-vaults" element={<HarpocrateVaultsPage />} />
```

- [ ] **Step 4: Créer la page squelette**

```tsx
// frontend/src/pages/HarpocrateVaultsPage.tsx
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function HarpocrateVaultsPage() {
  const { t } = useTranslation("harpocrate");
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedVaultId = searchParams.get("vault");

  return (
    <div className="flex h-full">
      <div className="text-slate-600 p-6">
        {t("page.title")} — squelette (T4-T10 à venir)
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Créer le fichier i18n harpocrate vide (sera complété T11)**

`frontend/src/i18n/fr/harpocrate.json` et `frontend/src/i18n/en/harpocrate.json` :
```json
{
  "page": { "title": "Coffres Harpocrate" }
}
```

Enregistrer le namespace dans `i18n.ts`.

- [ ] **Step 6: Smoke build + dev server**

```powershell
cd frontend
npx tsc --noEmit
npm run build
```

Manuellement : `npm run dev`, naviguer vers `http://localhost:5173/settings/harpocrate-vaults`, vérifier que le sidebar affiche la section Configuration et que le clic mène à la page squelette.

- [ ] **Step 7: Commit**

```powershell
cd ..
git add frontend/src/components/Sidebar.tsx frontend/src/routes.tsx frontend/src/pages/HarpocrateVaultsPage.tsx frontend/src/i18n/
git commit -m "feat(M5cd-front): sidebar Configuration + route /settings/harpocrate-vaults"
```

---

## Task 4: VaultsList + état vide + warning DEK + sélection URL

**Files:**
- Create: `frontend/src/pages/harpocrate/VaultsList.tsx`
- Create: `frontend/src/pages/harpocrate/VaultsEmptyState.tsx`
- Modify: `frontend/src/pages/HarpocrateVaultsPage.tsx`

- [ ] **Step 1: Implémenter `VaultsList`**

Composant 240px, fond blanc, border-right. Affiche :
- Titre "Coffres" + bouton "+ Nouveau" (déclenche prop `onCreate`)
- Liste des coffres via `useVaults()`. Chaque item :
  - Active (selected) : `bg-sky-50 border-l-4 border-sky-600`
  - Inactive : hover effect léger
  - Affiche `name` + sous-titre (`default · label` ou juste `label`)
  - Indicateur `●` vert (default) ou gris
- Si liste vide → affiche `VaultsEmptyState` à la place

Props : `selectedId: string | null`, `onSelect: (id: string) => void`, `onCreate: () => void`

- [ ] **Step 2: Implémenter `VaultsEmptyState`**

Centré, icône 🔐 (ou Lucide `KeyRound`), titre, sous-titre, bouton "+ Créer mon premier coffre" (prop `onCreate`).

**Warning DEK manquant** : pour détecter, on tente `createVault` et on intercepte 503. Mais on n'a pas encore le dialog T7. Pour M5cd-F-T4, on affiche juste l'état vide sans warning. Le warning sera ajouté en T7 ou T11.

- [ ] **Step 3: Câbler la page HarpocrateVaultsPage**

```tsx
export function HarpocrateVaultsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("vault");
  const [createOpen, setCreateOpen] = useState(false);

  const handleSelect = (id: string) => {
    setSearchParams({ vault: id }, { replace: true });
  };

  return (
    <div className="flex h-full bg-slate-50">
      <VaultsList
        selectedId={selectedId}
        onSelect={handleSelect}
        onCreate={() => setCreateOpen(true)}
      />
      <div className="flex-1 bg-white p-6">
        {/* T5 : VaultDetailPanel — placeholder pour l'instant */}
        {selectedId ? (
          <div>Détail coffre {selectedId} — T5+ à venir</div>
        ) : (
          <div className="text-slate-400 italic">Sélectionne un coffre à gauche</div>
        )}
      </div>
      {/* T7 : <CreateVaultDialog open={createOpen} onOpenChange={setCreateOpen} /> */}
    </div>
  );
}
```

- [ ] **Step 4: Auto-sélection au premier load**

Si `useVaults().data` arrive non-vide ET `selectedId === null`, sélectionner le premier coffre `is_default` (ou premier de la liste). Utiliser `useEffect`.

- [ ] **Step 5: Smoke build + manuel**

```powershell
cd frontend
npx tsc --noEmit && npm run lint
npm run dev
```

Vérifier la page. Si LXC 303 a déjà un coffre, on doit le voir. Sinon état vide.

- [ ] **Step 6: Commit**

```powershell
cd ..
git add frontend/src/pages/harpocrate/ frontend/src/pages/HarpocrateVaultsPage.tsx
git commit -m "feat(M5cd-front): VaultsList + état vide + sélection URL-synced"
```

---

## Task 5: VaultDetailPanel structure (header + tabs)

**Files:**
- Create: `frontend/src/pages/harpocrate/VaultDetailPanel.tsx`
- Create: `frontend/src/pages/harpocrate/VaultHeader.tsx`
- Modify: `frontend/src/pages/HarpocrateVaultsPage.tsx`

- [ ] **Step 1: Implémenter `VaultHeader`**

Props : `vault: VaultSummary`, `lastTest: VaultTestConnectionResult | null`, `onTest: () => void`, `onMenu: (action) => void`.

Layout : flex justify-between, border-bottom. À gauche : nom + badges (default si applicable + healthy/auth-ko si lastTest) + sous-titre `label · base_url`. À droite : bouton "Tester" (primary sky-600) + bouton `⋯` (menu shadcn DropdownMenu pour set-default / autre actions ultérieures).

Badges via shadcn `Badge` ou className Tailwind directe.

- [ ] **Step 2: Implémenter `VaultDetailPanel`**

Container max-width 760px (Tailwind `max-w-[760px]`), padding `px-7 py-5`.

Props : `vaultId: string`.

Charge `useVault(vaultId)`. Tant que loading → spinner. Si error → affichage erreur.

State local : `activeTab: "detail" | "secrets" | "info"` (default `"detail"`).

Structure :
- `<VaultHeader>` en haut
- Tabs (shadcn `Tabs`) : Détail / Secrets / Info wallet
- Contenu placeholder par tab pour l'instant (T6/T8/T9 rempliront)

- [ ] **Step 3: Câbler dans `HarpocrateVaultsPage`**

Remplacer le placeholder de T4 par `<VaultDetailPanel vaultId={selectedId} />` quand `selectedId !== null`.

- [ ] **Step 4: Smoke + commit**

```powershell
cd frontend && npx tsc --noEmit && npm run lint
cd ..
git add frontend/src/pages/harpocrate/VaultDetailPanel.tsx frontend/src/pages/harpocrate/VaultHeader.tsx frontend/src/pages/HarpocrateVaultsPage.tsx
git commit -m "feat(M5cd-front): VaultDetailPanel structure (header + 3 tabs)"
```

---

## Task 6: VaultDetailTab (formulaire édition + save)

**Files:**
- Create: `frontend/src/pages/harpocrate/VaultDetailTab.tsx`
- Modify: `frontend/src/pages/harpocrate/VaultDetailPanel.tsx` (câbler le tab)

- [ ] **Step 1: Implémenter `VaultDetailTab`**

Props : `vault: VaultSummary`, `onReplaceApiKey: () => void`, `onReveal: () => void`, `onRetire: () => void`.

Form (react-hook-form ou state local — react-hook-form déjà utilisé dans M5b cf. WorkspaceCreateDialog) :
- `name` : input disabled, valeur initiale `vault.name`
- `label` : input texte, defaultValue `vault.label`
- `base_url` : input texte, defaultValue `vault.base_url`
- `api_key_id` : input disabled, valeur `vault.api_key_id`, à côté boutons "Remplacer la clé" (open ReplaceApiKeyDialog T10) et "Reveal" (open RevealApiKeyDialog T10)
- `probe_path` : input texte, defaultValue `vault.probe_path ?? ""`, placeholder "laissé vide → whoami()"

Footer (border-top) :
- Gauche : bouton "Retirer ce coffre" (rouge outline) → `onRetire()`
- Droite : "Annuler" (reset form) + "Enregistrer" (submit)

Submit → `useUpdateVault(vault.id).mutate({ label, base_url, probe_path })`. Optimistic update via React Query.

Erreurs : toast `useToast` (M5b existant) en cas d'échec.

- [ ] **Step 2: Câbler dans `VaultDetailPanel`**

Quand `activeTab === "detail"` → `<VaultDetailTab vault={...} onReplaceApiKey={...} onReveal={...} onRetire={...} />`.

Les handlers `onReplaceApiKey`/`onReveal`/`onRetire` ouvrent les dialogs (T10). En T6, on les laisse comme stubs : `() => alert("T10 à venir")`.

- [ ] **Step 3: Smoke + commit**

```powershell
cd frontend && npx tsc --noEmit && npm run lint
cd ..
git add frontend/src/pages/harpocrate/VaultDetailTab.tsx frontend/src/pages/harpocrate/VaultDetailPanel.tsx
git commit -m "feat(M5cd-front): VaultDetailTab formulaire + save"
```

---

## Task 7: CreateVaultDialog

**Files:**
- Create: `frontend/src/pages/harpocrate/CreateVaultDialog.tsx`
- Modify: `frontend/src/pages/HarpocrateVaultsPage.tsx`
- Modify: `frontend/src/pages/harpocrate/VaultsEmptyState.tsx` (warning DEK)

- [ ] **Step 1: Implémenter `CreateVaultDialog`**

shadcn `Dialog` width 480px. react-hook-form + Zod (déjà installé M5b).

Schema Zod : name (regex `/^[a-z][a-z0-9_-]{2,63}$/`), label (min 1), base_url (URL valide commençant par http), api_key_id (min 1), api_key (min 8), is_default (boolean).

Submit → `useCreateVault().mutate(payload, { onSuccess: closeDialog + select new vault, onError: setErrorState })`.

Gestion erreurs :
- 409 (duplicate name) : afficher message sous champ `name`
- 422 (validation) : afficher message global
- 503 (DEK manquant) : remplacer le contenu du dialog par un encart rouge "HARPOCRATE_DEK absent côté backend"

Props : `open: boolean`, `onOpenChange: (open: boolean) => void`, `onCreated: (vault: VaultSummary) => void`.

- [ ] **Step 2: Ajouter détection DEK manquant dans `VaultsEmptyState`**

Tenter un `useVaults()` (déjà fait) — si on a une réponse mais que `createVault` retourne 503, c'est qu'il manque le DEK. Pour M5cd, plus simple : ne PAS afficher le warning a priori. Le warning apparaît UNIQUEMENT après une tentative de création qui répond 503. Le state local du dialog gère ça.

Alternative : on peut afficher le warning DEK dans l'état vide en testant `createVault({ ... })` avec un payload dummy, mais c'est sale. **Décision T7 : warning UNIQUEMENT dans le dialog après échec 503.**

- [ ] **Step 3: Câbler dans HarpocrateVaultsPage**

```tsx
<CreateVaultDialog
  open={createOpen}
  onOpenChange={setCreateOpen}
  onCreated={(vault) => {
    setSearchParams({ vault: vault.id });
    setCreateOpen(false);
  }}
/>
```

- [ ] **Step 4: Smoke + commit**

```powershell
cd frontend && npx tsc --noEmit && npm run lint && npm run build
cd ..
git add frontend/src/pages/harpocrate/CreateVaultDialog.tsx frontend/src/pages/HarpocrateVaultsPage.tsx
git commit -m "feat(M5cd-front): CreateVaultDialog + gestion 409/422/503"
```

---

## Task 8: VaultSecretsTab (filtres + table + copy)

**Files:**
- Create: `frontend/src/pages/harpocrate/VaultSecretsTab.tsx`
- Modify: `frontend/src/pages/harpocrate/VaultDetailPanel.tsx`

- [ ] **Step 1: Implémenter `VaultSecretsTab`**

Props : `vaultId: string`, `enabled: boolean`.

State local : `filters: { name_contains?: string; path?: string; tag?: string }`, debounced sur `name_contains` (300ms).

Charge `useVaultSecrets(vaultId, filters, enabled)`. Loading → spinner. Error 502 → encart erreur + bouton Réessayer.

UI :
- Barre filtres (3 inputs/selects) en haut
- Table 4 colonnes : Nom (monospace), Description, Type (badge `secret` bleu / `placeholder` ambre), bouton "📋 Copier" (utilise `navigator.clipboard.writeText(name)`)
- Footer pagination : si `next_cursor` non-null, bouton "Charger 50 de plus" (à implémenter ou laisser stub "TODO pagination" — décider).

Pour M5cd-F-T8, **pas de pagination** (l'admin a typiquement <50 secrets). Juste afficher le compteur "Affichés N / next_cursor disponible".

- [ ] **Step 2: Câbler dans VaultDetailPanel**

Quand `activeTab === "secrets"` → `<VaultSecretsTab vaultId={vault.id} enabled={true} />`. Le `enabled=true` ne se déclenche que quand le tab est actif (via le rendering conditionnel) — donc lazy load naturel.

- [ ] **Step 3: Smoke + commit**

```powershell
cd frontend && npx tsc --noEmit && npm run lint
cd ..
git add frontend/src/pages/harpocrate/VaultSecretsTab.tsx frontend/src/pages/harpocrate/VaultDetailPanel.tsx
git commit -m "feat(M5cd-front): VaultSecretsTab filtres + table + copy"
```

---

## Task 9: VaultWalletInfoTab

**Files:**
- Create: `frontend/src/pages/harpocrate/VaultWalletInfoTab.tsx`
- Modify: `frontend/src/pages/harpocrate/VaultDetailPanel.tsx`

- [ ] **Step 1: Implémenter `VaultWalletInfoTab`**

Props : `vaultId: string`, `enabled: boolean`.

Charge `useVaultWalletInfo(vaultId, enabled)`. Error 502 → encart + bouton Réessayer.

UI : 2 sections (Wallet + API key) avec layout `grid-cols-[130px_1fr]` :
- Wallet : `wallet_name` (ou "—") + `wallet_id` (monospace)
- API key : `api_key_id` (monospace) + permissions (badges bleus pour celles présentes, grises barrées pour les autres : `["read", "write", "add", "remove"]`) + `expires_at` (avec badge `+ N mois` ou `⚠ expire bientôt` si <30j ou rouge si expirée)

Helper : `function formatExpires(date: string | null)` retourne `{ formatted: "2027-01-15", badge: { tone: "ok"|"warn"|"error", text: "+ 8 mois" } }`.

- [ ] **Step 2: Câbler dans VaultDetailPanel**

Quand `activeTab === "info"` → `<VaultWalletInfoTab vaultId={vault.id} enabled={true} />`.

- [ ] **Step 3: Smoke + commit**

```powershell
cd frontend && npx tsc --noEmit && npm run lint
cd ..
git add frontend/src/pages/harpocrate/VaultWalletInfoTab.tsx frontend/src/pages/harpocrate/VaultDetailPanel.tsx
git commit -m "feat(M5cd-front): VaultWalletInfoTab (wallet + permissions + expiration)"
```

---

## Task 10: Dialogs ReplaceApiKey + Reveal + Retire + SetDefault + Test toast

**Files:**
- Create: `frontend/src/pages/harpocrate/ReplaceApiKeyDialog.tsx`
- Create: `frontend/src/pages/harpocrate/RevealApiKeyDialog.tsx`
- Create: `frontend/src/pages/harpocrate/RetireVaultDialog.tsx`
- Modify: `frontend/src/pages/harpocrate/VaultDetailPanel.tsx` (câbler dialogs + test toast)
- Modify: `frontend/src/pages/harpocrate/VaultHeader.tsx` (menu ⋯ avec SetDefault)
- Modify: `frontend/src/pages/harpocrate/VaultDetailTab.tsx` (câbler handlers)

- [ ] **Step 1: Implémenter `ReplaceApiKeyDialog`**

Props : `vaultId: string`, `currentApiKeyId: string`, `open: boolean`, `onOpenChange`, `onReplaced: () => void`.

Dialog avec explication claire (i18n key `harpocrate.replace_dialog.explanation`) + 2 champs : `api_key_id`, `api_key` (type password). Submit → `useReplaceApiKey(vaultId).mutate({ api_key_id, api_key })`. Toast succès / error.

- [ ] **Step 2: Implémenter `RevealApiKeyDialog`**

Deux states : `confirmed: boolean` (avant clic), `revealed: { value: string } | null` (après clic réussi).

Étape 1 : message warning + bouton "Afficher la clé" (déclenche `useRevealApiKey(vaultId).mutate()`)
Étape 2 : input readonly avec valeur masquée par défaut (type=password), boutons "👁 Afficher / Masquer" (toggle local state) et "📋 Copier" (clipboard).

Au close du dialog : reset le state, ne pas garder la valeur en mémoire.

- [ ] **Step 3: Implémenter `RetireVaultDialog`**

Props : `vault: VaultSummary`, `walletName: string | null`, `open: boolean`, `onOpenChange`, `onRetired: () => void`.

Wording exact (i18n) : "Le wallet Harpocrate distant `{wallet_name}` ne sera pas supprimé. Seule la configuration locale est retirée." Si `walletName` null (info wallet pas chargée) → "Le wallet Harpocrate distant ne sera pas supprimé...".

Input "Pour confirmer, tape le nom du coffre : `{vault.name}`". Bouton "Retirer" désactivé tant que l'input ne matche pas. Submit → `useDeleteVault().mutate(vault.id)`.

Erreur 409 (default + autres) → message inline "Désigne un autre coffre par défaut d'abord".

- [ ] **Step 4: Câbler les dialogs dans VaultDetailPanel + VaultDetailTab**

State local dans `VaultDetailPanel` : `dialogOpen: "replace" | "reveal" | "retire" | null`. Passe `onReplaceApiKey={() => setDialog("replace")}` etc. aux composants enfants. Render les 3 dialogs avec `open={dialogOpen === "..."}`.

- [ ] **Step 5: Menu ⋯ du VaultHeader avec SetDefault**

`VaultHeader` utilise `DropdownMenu` (shadcn). Items :
- "Désigner comme coffre par défaut" (désactivé si `vault.is_default`) → `useSetDefaultVault().mutate(vault.id)` + toast
- Séparateur
- "Retirer ce coffre" → `onRetire()` (passe au parent)

- [ ] **Step 6: Test connection toast + badge update**

Dans `VaultHeader`, bouton "Tester" → `useTestConnection(vault.id).mutate()`. `onSuccess(result)` → toast vert/rouge selon `result.ok`, et le badge healthy/auth-ko est mis à jour via `useLastTestResult(vault.id)`.

- [ ] **Step 7: Smoke + commit**

```powershell
cd frontend && npx tsc --noEmit && npm run lint
cd ..
git add frontend/src/pages/harpocrate/
git commit -m "feat(M5cd-front): dialogs ReplaceApiKey/Reveal/Retire + SetDefault + test toast"
```

---

## Task 11: i18n complet + tests Vitest

**Files:**
- Modify: `frontend/src/i18n/fr/harpocrate.json` (complet)
- Modify: `frontend/src/i18n/en/harpocrate.json` (complet)
- Create: `frontend/src/pages/harpocrate/__tests__/VaultsList.test.tsx`
- Create: `frontend/src/pages/harpocrate/__tests__/VaultDetailTab.test.tsx`
- Create: `frontend/src/pages/harpocrate/__tests__/CreateVaultDialog.test.tsx`
- Create: `frontend/src/pages/harpocrate/__tests__/RetireVaultDialog.test.tsx`
- Create: `frontend/src/pages/harpocrate/__tests__/VaultSecretsTab.test.tsx`

- [ ] **Step 1: Compléter i18n FR + EN**

Recopier intégralement le namespace `harpocrate` de la spec §6 (sections page/list/header/tabs/detail/secrets/info/create_dialog/replace_dialog/reveal_dialog/retire_dialog/test_toast). Idem en anglais avec traduction directe.

- [ ] **Step 2: Vérifier 0 string brute hardcodée dans les composants**

```powershell
cd frontend
grep -rn '"[A-Z][a-zA-Z ]\+"' src/pages/harpocrate/ | grep -v "import\|from"
```

Toute chaîne user-facing doit passer par `useTranslation`. Corriger les manquements.

- [ ] **Step 3: Écrire les tests Vitest**

Pattern : `vi.mock("@/hooks/useHarpocrateVaults")`, render avec `QueryClientProvider`, assert sur DOM via React Testing Library.

5 fichiers de tests, ~30 cas au total :
- `VaultsList.test.tsx` : liste avec données / vide / sélection
- `VaultDetailTab.test.tsx` : rendu form / save / Retire/Replace/Reveal handlers
- `CreateVaultDialog.test.tsx` : submit / 409 / 422 / 503 DEK warning
- `RetireVaultDialog.test.tsx` : input confirmation / submit bloqué si nom mismatch / 409 default
- `VaultSecretsTab.test.tsx` : filtres / table / copy clipboard

- [ ] **Step 4: Run tests**

```powershell
cd frontend
npm test
```

Expected : tous verts.

- [ ] **Step 5: Build complet**

```powershell
npx tsc --noEmit
npm run build
npm run lint
```

Expected : clean.

- [ ] **Step 6: Commit**

```powershell
cd ..
git add frontend/src/i18n/ frontend/src/pages/harpocrate/__tests__/
git commit -m "feat(M5cd-front): i18n complet FR+EN + tests Vitest (5 fichiers)"
```

---

## Task 12: Deploy LXC 303 + smoke + tag

- [ ] **Step 1: Push origin dev**

```powershell
git push origin dev
```

- [ ] **Step 2: Deploy LXC 303**

```powershell
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Expected : `Smoke /health → ok`, version reporte le SHA M5cd.

- [ ] **Step 3: Smoke manuel UI**

Ouvrir `http://192.168.10.184/ui/settings/harpocrate-vaults`. Vérifier :
1. Sidebar affiche section "Configuration" avec item "Coffres Harpocrate" actif
2. État vide visible (LXC 303 a probablement aucun coffre)
3. Cliquer "+ Créer mon premier coffre" → dialog s'ouvre
4. Tenter une création avec données factices → 422 ou 503 selon la config DEK
5. Si DEK posé : créer un vrai coffre, voir apparaître dans la liste, sélectionner, voir le panneau détail avec les 3 tabs

- [ ] **Step 4: Tag**

```powershell
git tag m5cd-frontend-done
git push origin m5cd-frontend-done
```

---

## Self-Review

### Couverture spec → tâches

| Section spec | Tâche(s) |
|---|---|
| §3 Architecture / découpage composants | Tasks 3-10 |
| §4 Couche API client | Task 1 |
| §5 Hooks React Query | Task 2 |
| §6 Internationalisation | Tasks 3 (skeleton) + 11 (complet) |
| §7 États et erreurs | Couverts inline dans T4 (vide, DEK) + T7 (création) + T9 (502) + T10 (dialogs) |
| §8 Tests | Task 11 |
| §9 Performance et UX (lazy load, debounce, optimistic) | Couverts dans T6 (optimistic) + T8 (debounce, lazy) + T9 (lazy) |
| §11 Critères complétion | Task 12 |
| §12 Pièges | Adressés inline (URL state T4, auto-sélection T4, name immuable T6, etc.) |

### Placeholder scan

Aucun "TBD" / "TODO" / "implement later". Chaque step est actionnable.

### Cohérence types

- 9 types TS définis en T1, consommés dans T2-T10
- Pattern hooks `[...ROOT_KEY, id, "...]"` cohérent dans T2
- Props composants cohérentes T4-T10

### Bite-sized check

12 tâches, chacune 3-7 steps. Plus court que M5c-backend. T1-T2 sans UI (purement TS), T3-T10 incrémentent l'UI brique par brique, T11 finalise polish, T12 déploie.
