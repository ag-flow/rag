# M5cd-frontend — Page Settings UI Coffres Harpocrate (design)

**Date** : 2026-05-17
**Statut** : design (à reviewer)
**Portée** : frontend uniquement. Consomme les endpoints livrés en M5c-backend (CRUD coffres) + M5d-backend (whoami/info, types, list secrets).
**Précédent** : M5c-backend (`m5c-backend-done`), M5d-backend (`m5d-backend-done`), M5b-frontend (sidebar D1 v2 + page Workspaces).

## 1. Objectif

Permettre à l'admin RAG de gérer **les coffres Harpocrate** (les serveurs Harpocrate + tokens d'accès au wallet) sans toucher au `.env` et sans curl. Concrètement : CRUD des entrées de la table `harpocrate_vaults`, test de connexion visuel, navigation des secrets disponibles dans le coffre, lecture des métadonnées du wallet.

Cette page sert aussi de **fondation pour les futurs réglages** (OIDC config, modèles, etc.) sous la nouvelle section "Configuration" du sidebar.

## 2. Décisions de conception (brainstorming validé)

| # | Question | Décision |
|---|---|---|
| Q1 | Nav | Section "Configuration" dédiée dans sidebar gauche, item "Coffres Harpocrate", route `/settings/harpocrate-vaults` |
| Q2 | Layout principal | Master-detail (liste compacte gauche 240px + panneau détail droite avec contenu max-width 760px) |
| Q3 | Structure panneau détail | 3 tabs internes : **Détail** / **Secrets** / **Info wallet** |
| Q4 | Action "rotation" | Renommée **"Remplacer la clé"** — Harpocrate ne génère pas de nouvelles api_keys côté serveur, l'admin colle ici un token créé au préalable côté Harpocrate UI |
| Q5 | Reveal api_key | Dialog modal de confirmation (audit-loggué via backend) ; affichage masqué-par-défaut + toggle + copier |
| Q6 | Delete coffre | Dialog avec input "tape le nom pour confirmer". **Wording "Retirer ce coffre"** (pas "Supprimer") — la suppression ne touche QUE la table locale, le wallet Harpocrate distant n'est pas affecté |
| Q7 | Feedback test_connection | Toast (vert/rouge) + mise à jour du badge `● healthy` / `● auth ko` dans le header du coffre |
| Q8 | DEK manquant | Encart d'avertissement rouge dans l'état vide ET dans le dialog création si l'API répond 503 (ou si on détecte au boot) |
| Q9 | Création coffre | Dialog modal centré 480px déclenché par "+ Nouveau" dans la liste |
| Q10 | État vide | Icône + texte d'explication + bouton "+ Créer mon premier coffre" |

## 3. Architecture cible

### 3.1 Nav et routes

**Sidebar enrichi** (`components/Sidebar.tsx`) : ajout d'une 3ᵉ section après "Usage" :

```
Administration
  - Workspaces (active)
  - Sources (disabled)
  - Jobs (disabled)
  - Models (disabled)
Usage
  - Push (disabled)
  - MCP (disabled)
Configuration                       ← NOUVELLE
  - Coffres Harpocrate              ← actif, /settings/harpocrate-vaults
```

**Routes** (`routes.tsx`) : ajout `<Route path="/settings/harpocrate-vaults" element={<HarpocrateVaultsPage />} />`. La route `/settings` seule redirige vers le premier item de configuration disponible.

### 3.2 Layout master-detail

```
┌─ Sidebar app ─┬──────────────────────────────────────────────────────┐
│ (déjà M5b)    │ ┌─ Liste coffres (240px) ─┬─ Panneau détail ────────┐│
│               │ │ + Nouveau               │ Header coffre + actions ││
│               │ │ ● rag (default) actif   │ ─────────────────────── ││
│               │ │ ● staging               │ [Détail|Secrets|Info]   ││
│               │ │ ● prod-eu               │ … contenu tab actif …   ││
│               │ │                         │     (max-width 760px)   ││
│               │ └─────────────────────────┴──────────────────────────┘│
└───────────────┴──────────────────────────────────────────────────────┘
```

### 3.3 Découpage des composants

| Composant | Responsabilité |
|---|---|
| `HarpocrateVaultsPage` | Container page : layout master-detail + state sélection courante (useState ou URL param `?vault=<id>`) |
| `VaultsList` | Liste compacte gauche + bouton "+ Nouveau". Highlight item actif. Vide → `VaultsEmptyState`. |
| `VaultDetailPanel` | Panneau droit : header + tabs + contenu. Reçoit `vault_id` en prop. Charge les détails via React Query. |
| `VaultHeader` | Nom + badges (default, healthy/ko) + boutons header (Tester, menu ⋯) |
| `VaultDetailTab` | Formulaire édition (label, base_url, probe_path) + actions `Remplacer la clé` / `Reveal` / footer Retirer/Annuler/Enregistrer |
| `VaultSecretsTab` | Filtres (nom, path, tag) + table secrets + bouton Copier |
| `VaultWalletInfoTab` | Lecture seule : sections Wallet + API key (badges permissions, expiration) |
| `VaultsEmptyState` | Icône + texte + CTA "+ Créer mon premier coffre". Encart DEK manquant conditionnel. |
| `CreateVaultDialog` | Modal 480px : formulaire création complet |
| `ReplaceApiKeyDialog` | Modal : explication + 2 champs (api_key_id, api_key) |
| `RevealApiKeyDialog` | Modal confirmation + affichage masqué/toggle/copier |
| `RetireVaultDialog` | Modal avec input "tape le nom" + bouton "Retirer" |

## 4. Couche API client (`lib/api/harpocrate-vaults.ts`)

Étendre le client existant (`lib/api/client.ts` de M5b) avec les **12 méthodes** correspondant aux endpoints backend :

### 4.1 M5c — CRUD

```typescript
listVaults() → Promise<VaultSummary[]>
getVault(id) → Promise<VaultSummary>
createVault(payload: VaultCreateRequest) → Promise<VaultSummary>
updateVault(id, payload: VaultUpdateRequest) → Promise<VaultSummary>
deleteVault(id) → Promise<void>
replaceApiKey(id, payload: VaultRotateApiKeyRequest) → Promise<VaultSummary>
setDefault(id) → Promise<VaultSummary>
testConnection(id) → Promise<VaultTestConnectionResult>
revealApiKey(id) → Promise<VaultRevealApiKeyResponse>
```

### 4.2 M5d — Enrichissements

```typescript
getWalletInfo(id) → Promise<WalletInfoResponse>
listVaultTypes(id, params?: { q?: string; include_deprecated?: boolean }) → Promise<SecretTypeSummary[]>
listVaultSecrets(id, params?: { path?: string; name_contains?: string; tag?: string; limit?: number }) → Promise<SecretListResponse>
```

### 4.3 Types TypeScript

Miroirs des schemas Pydantic backend, fichier `lib/api/harpocrate-vaults.types.ts` :

```typescript
export type VaultSummary = {
  id: string; name: string; label: string; base_url: string;
  api_key_id: string; probe_path: string | null;
  is_default: boolean; created_at: string; updated_at: string;
};

export type VaultCreateRequest = {
  name: string; label: string; base_url: string;
  api_key_id: string; api_key: string;
  probe_path?: string | null; is_default?: boolean;
};

export type VaultUpdateRequest = {
  label?: string; base_url?: string; probe_path?: string | null;
};

export type VaultRotateApiKeyRequest = {
  api_key_id: string; api_key: string;
};

export type VaultTestConnectionResult = {
  ok: boolean; detail: string; probe_path_used: string;
};

export type VaultRevealApiKeyResponse = {
  id: string; api_key_id: string; api_key: string;
};

export type WalletInfoResponse = {
  wallet_id: string; wallet_name: string | null;
  api_key_id: string; permissions: string[];
  api_key_expires_at: string | null;
};

export type SecretTypeSummary = {
  type_uuid: string; type: string; sous_type: string | null;
  label: string; deprecated: boolean;
};

export type SecretListItem = {
  id: string; name: string; description: string | null;
  is_placeholder: boolean; tags: string[];
};

export type SecretListResponse = {
  secrets: SecretListItem[]; next_cursor: string | null;
};
```

## 5. Hooks React Query (`hooks/useHarpocrateVaults.ts`)

Un fichier par groupe d'opérations, ou un fichier unique :

```typescript
useVaults()                            // queryKey: ["vaults"]
useVault(id)                           // queryKey: ["vaults", id]
useVaultWalletInfo(id, enabled)        // queryKey: ["vaults", id, "info"]
useVaultSecrets(id, filters, enabled)  // queryKey: ["vaults", id, "secrets", filters]
// useVaultTypes : pas de hook en M5cd-frontend (cf. §10 hors scope) — la méthode
// client `listVaultTypes` est exposée pour usage futur mais pas branchée à l'UI.

useCreateVaultMutation()
useUpdateVaultMutation()
useDeleteVaultMutation()
useReplaceApiKeyMutation()
useSetDefaultMutation()
useTestConnectionMutation()
useRevealApiKeyMutation()
```

**Invalidations** :
- create/update/delete/replace/setDefault → invalide `["vaults"]` (re-fetch liste) et `["vaults", id]` si applicable.
- testConnection : ne modifie pas le state serveur. On stocke localement la `lastTestResult` dans le store React Query via `queryClient.setQueryData(["vaults", id, "lastTest"], result)` pour permettre au badge du header de refléter l'état.
- reveal : pas de cache (chaque appel = audit log côté backend).

**Lazy loading** :
- `useVaultWalletInfo` et `useVaultSecrets` ont `enabled` contrôlé par l'onglet actif (pas de fetch si tab pas ouvert). Évite les appels SDK inutiles.

## 6. Internationalisation (i18n)

Tous les labels passent par `useTranslation()`. Nouveau namespace `harpocrate` dans `i18n/fr.json` + `i18n/en.json` :

```json
{
  "harpocrate": {
    "page": {
      "title": "Coffres Harpocrate",
      "subtitle": "Configurer les coffres-forts utilisés par le backend pour résoudre les secrets externes."
    },
    "list": {
      "new": "+ Nouveau",
      "empty_title": "Aucun coffre Harpocrate",
      "empty_subtitle": "Les api keys des modèles externes…",
      "empty_cta": "+ Créer mon premier coffre",
      "dek_warning": "HARPOCRATE_DEK absent côté backend, ajoutez-le dans le .env avant de créer un coffre."
    },
    "header": {
      "badge_default": "default",
      "badge_healthy": "● healthy",
      "badge_auth_ko": "● auth ko",
      "test": "Tester la connexion"
    },
    "tabs": {
      "detail": "Détail",
      "secrets": "Secrets",
      "info": "Info wallet"
    },
    "detail": {
      "name_label": "Nom (immuable)",
      "label_label": "Libellé",
      "base_url_label": "Base URL",
      "api_key_id_label": "api_key_id",
      "probe_path_label": "probe_path (optionnel)",
      "probe_path_placeholder": "laissé vide → whoami()",
      "replace_key": "Remplacer la clé",
      "reveal_key": "Reveal",
      "retire_vault": "Retirer ce coffre",
      "save": "Enregistrer",
      "cancel": "Annuler"
    },
    "secrets": {
      "filter_name": "🔍 Filtrer par nom...",
      "filter_path": "path/",
      "filter_tag": "Tag : tous",
      "col_name": "Nom",
      "col_description": "Description",
      "col_type": "Type",
      "type_secret": "secret",
      "type_placeholder": "placeholder",
      "copy": "📋 Copier",
      "more": "... {{count}} autres secrets"
    },
    "info": {
      "wallet_section": "Wallet",
      "wallet_name": "Nom",
      "wallet_id": "Wallet ID",
      "apikey_section": "API key (token utilisé)",
      "apikey_id": "api_key_id",
      "permissions": "Permissions",
      "expires_at": "Expire le"
    },
    "create_dialog": {
      "title": "Créer un nouveau coffre Harpocrate",
      "subtitle": "Connecte le backend à un serveur Harpocrate via une api_key existante.",
      "name_help": "^[a-z][a-z0-9_-]{2,63}$ — utilisé dans les refs ${vault://<nom>:path}",
      "set_default_label": "Désigner comme coffre par défaut",
      "submit": "Créer le coffre"
    },
    "replace_dialog": {
      "title": "Remplacer la clé d'accès",
      "explanation": "Vous devez avoir préalablement créé une nouvelle api_key dans l'UI Harpocrate. Collez ici son token et son identifiant. Le wallet associé reste le même.",
      "submit": "Remplacer"
    },
    "reveal_dialog": {
      "title": "Afficher la clé en clair",
      "warning": "Cette action est audit-loggée (vault.reveal dans Loki).",
      "confirm": "Afficher la clé",
      "toggle_show": "👁 Afficher",
      "toggle_hide": "👁 Masquer",
      "copy": "📋 Copier"
    },
    "retire_dialog": {
      "title": "Retirer ce coffre",
      "warning": "Le wallet Harpocrate distant {{wallet_name}} ne sera pas supprimé. Seule la configuration locale est retirée.",
      "confirm_label": "Pour confirmer, tape le nom du coffre :",
      "submit": "Retirer le coffre"
    },
    "test_toast": {
      "ok": "Connexion OK — {{detail}}",
      "ko": "Connexion KO — {{detail}}"
    }
  }
}
```

## 7. États et erreurs

### 7.1 Page-level

| État | Affichage |
|---|---|
| Liste en chargement | `LoadingSpinner` (existant M5b) plein écran |
| Liste vide | `VaultsEmptyState` avec CTA |
| Liste OK + aucun sélectionné | Liste à gauche + panneau droit avec invitation "Sélectionne un coffre" |
| Liste OK + sélection | Layout normal |
| Erreur 401 → redirige vers OIDC login (existant M5b `AuthGuard`) |

### 7.2 Erreurs API

- **`testConnection` retourne `ok=false`** : toast rouge avec `detail`, badge passe à `● auth ko`. La page reste utilisable.
- **`getWalletInfo` retourne 502** (Harpocrate inaccessible) : onglet "Info wallet" affiche un encart d'erreur + bouton "Réessayer".
- **`listVaultSecrets` retourne 502** : idem, onglet "Secrets" en erreur.
- **`createVault` retourne 409** (duplicate name) : message d'erreur dans le dialog en dessous du champ `name`.
- **`createVault` retourne 422** (slug invalide) : message d'erreur sous le champ correspondant.
- **`createVault` retourne 503** (DEK manquant) : remplace le dialog par l'encart DEK warning.
- **`deleteVault` retourne 409** (default + autres coffres) : message d'erreur dans le dialog Retirer (proposer "désigne un autre coffre par défaut d'abord").

### 7.3 Indicateurs visuels (cf. règle `StatusIndicator` existante)

- Badge `default` : jaune doux (`bg-amber-100 text-amber-800`).
- Badge `healthy` : vert (`bg-emerald-100 text-emerald-800` + `●` vert).
- Badge `auth ko` : rouge (`bg-rose-100 text-rose-800` + `●` rouge).
- Badge `expire bientôt` (< 30j) : orange (`bg-orange-100 text-orange-800`).
- Badge `expirée` : rouge.

## 8. Tests

### 8.1 Composants (Vitest + React Testing Library)

- `VaultsList.test.tsx` : rendu liste, sélection, état vide avec warning DEK
- `VaultDetailPanel.test.tsx` : 3 onglets, switch tab, badges header
- `VaultDetailTab.test.tsx` : édition, save, validation
- `VaultSecretsTab.test.tsx` : filtres, copie nom, pagination
- `VaultWalletInfoTab.test.tsx` : rendu sections, badge expiration
- `CreateVaultDialog.test.tsx` : validation form, submission, 409, 422, 503
- `ReplaceApiKeyDialog.test.tsx`
- `RevealApiKeyDialog.test.tsx` : toggle show/hide, copier
- `RetireVaultDialog.test.tsx` : input confirmation, 409 si default
- Mocks API : `vi.mock` du client `harpocrate-vaults.ts`

### 8.2 Page

- `HarpocrateVaultsPage.test.tsx` : layout master-detail, sélection initiale (premier coffre), URL `?vault=<id>` syncronisé

## 9. Performance et UX

- **Lazy loading** des tabs Secrets / Info wallet via `enabled` React Query.
- **Optimistic update** sur `updateVault` (label, base_url, probe_path) : le panneau reflète immédiatement les valeurs typées, rollback si l'API échoue.
- **Debounce** sur le filtre `name_contains` dans l'onglet Secrets (300ms).
- **Pagination** simple sur l'onglet Secrets : si `next_cursor` non-null, bouton "Charger 50 de plus" en bas de la table.
- **Cache** React Query : `staleTime: 30s` sur les queries lecture (liste, detail, info, secrets, types). Invalidation explicite sur les mutations.

## 10. Hors scope M5cd-frontend (jalons futurs)

| Feature | Statut | Pourquoi reporté |
|---|---|---|
| Catalogue types (utilisation de `useVaultTypes`) | Reporté | Pas d'écran qui le consomme en M5cd-frontend (sera utile quand on créera/éditera des secrets côté UI, hors scope) |
| Création de secrets via UI ag-flow.rag | Hors scope | L'admin crée ses secrets dans l'UI Harpocrate directement. Notre UI les consomme en lecture. |
| Auto-rotation des api keys (notify_auth_error) | Hors scope | M5e séparé (backend) |
| Page Settings multi-onglets (OIDC, modèles) | Reporté | M5cd-frontend ne pose que la page Coffres. La structure "Configuration" dans le sidebar prépare les futures pages. |
| `lastTest` persisté en DB | Hors scope | Stocké uniquement dans React Query cache (frontend). Disparaît au refresh. |

## 11. Critères de complétion M5cd-frontend

- Sidebar enrichi avec section "Configuration" + item "Coffres Harpocrate"
- Route `/settings/harpocrate-vaults` accessible
- Page complète : liste + panneau détail + 3 onglets fonctionnels
- 4 dialogs : Create / ReplaceApiKey / Reveal / Retire
- État vide + warning DEK manquant
- Toast feedback test_connection + badge mis à jour
- i18n FR + EN complet
- Tests Vitest sur les composants clés
- `npm run build` clean, `npx tsc --noEmit` clean, `npm run lint` clean
- Déployé sur LXC 303 via `./dev-deploy.sh`
- Smoke manuel : créer/modifier/tester/retirer un coffre via UI sur LXC 303
- Tag `m5cd-frontend-done`

## 12. Pièges anticipés

1. **`useState` vs URL state pour la sélection** : préférer URL param `?vault=<id>` pour permettre le partage de lien et le refresh sans perte d'état. Pattern React Router `searchParams`.
2. **Auto-sélection** : au premier load, si liste non-vide et aucun `?vault=` dans l'URL, sélectionner le premier coffre is_default (ou premier de la liste à défaut).
3. **`name` immuable** : l'input est `disabled` en édition. Le backend rejette `name` dans PATCH via `extra="forbid"` (M5c-T4).
4. **`is_default` non-modifiable dans PATCH** : passe par `useSetDefaultMutation` séparé. Dans le panneau Détail, pas de toggle ; action "Désigner par défaut" dans le menu ⋯.
5. **Mock `MagicMock(name=...)` dans tests Python** ne s'applique pas ici (Vitest ≠ unittest.mock). On utilise `vi.mock` standard.
6. **CORS** : pas de souci car le frontend est servi via Caddy sur le même origine que le backend (`/api/*` → backend:8000).
7. **Reveal après page refresh** : le composant ne pré-charge JAMAIS la valeur en clair. Toujours un clic explicite + confirmation.
8. **Test connection sans coffre sélectionné** : bouton inactif.
9. **DEK manquant** : on détecte via la réponse 503 du create. Pas d'endpoint dédié "health DEK" (à éviter pour la sécurité, ne pas exposer l'état du chiffrement côté UI).

## 13. Suite

1. User review de cette spec
2. Plan TDD dans `docs/superpowers/plans/2026-05-17-M5cd-frontend-harpocrate-vaults.md`
3. Exécution subagent-driven
4. Déploiement LXC 303 via `./dev-deploy.sh`
5. Tag `m5cd-frontend-done`
