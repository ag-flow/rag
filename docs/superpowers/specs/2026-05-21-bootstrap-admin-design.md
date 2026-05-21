# Bootstrap admin local + page OIDC accessible — design

**Date** : 2026-05-21
**Statut** : design, en attente de revue
**Auteur** : architecte (brainstorm)

## 1. Contexte

L'IHM `ag-flow.rag` ne peut être atteinte qu'après authentification, et la seule
méthode d'authentification IHM disponible est OIDC (Keycloak). Or l'OIDC se
configure via `OidcConfigPage` (`frontend/src/pages/OidcConfigPage.tsx`), qui est
elle-même protégée par `AuthGuard`. Conséquence : sur un déploiement neuf, l'IHM
est inaccessible tant que l'OIDC n'est pas configuré, et l'OIDC ne peut pas
être configuré depuis l'IHM. Un opérateur ne peut s'en sortir qu'en envoyant
manuellement un `POST /api/admin/oidc` avec la master-key via `curl`.

Le `POST /api/admin/oidc` accepte déjà la master-key (cf.
`backend/src/rag/api/admin_oidc.py:14`), donc le mécanisme bas-niveau existe.
Ce qui manque est un **chemin d'authentification IHM** utilisable avant qu'OIDC
ne soit configuré.

## 2. Objectif

Ajouter un **bootstrap admin local** : un compte `admin` unique, authentifié par
username + password (hash bcrypt stocké dans `.env`), qui ouvre une session IHM
classique avec le rôle `rag-admin`. Ce compte permet à l'opérateur de se
connecter, paramétrer OIDC via l'IHM existante, puis basculer sur SSO.

Le bootstrap n'est **pas** auto-désactivé après configuration d'OIDC : il reste
disponible tant que `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` est défini dans `.env`.
C'est un mécanisme de secours permanent, à la discrétion de l'opérateur.

## 3. Cadrage et décisions

| Décision | Choix retenu | Justification |
|---|---|---|
| Activation du bootstrap | Toujours actif si `.env` le déclare | L'opérateur coupe en retirant la var et redémarrant. Pas de logique implicite. |
| Algorithme de hash | bcrypt (`bcrypt>=4.2` déjà en deps backend) | Résistant brute-force, déjà disponible, format `$2b$…` portable. |
| Outil de hash dans `dev-deploy.sh` | `openssl passwd -bcrypt` | `openssl` est ubiquitaire, pas de dépendance système nouvelle. |
| Source du password en clair | Généré aléatoirement par `dev-deploy.sh`, affiché en console | Même modèle que `POSTGRES_PASSWORD` existant. Pas de prompt interactif. |
| Identité du compte | Username fixe `admin`, rôle synthétique `rag-admin` | Un seul user bootstrap suffit. Pas de var `USERNAME` séparée. |
| UX login | Page React unique `/ui/login` avec bouton SSO + form local | Une seule entrée, état rendu selon `GET /api/auth/methods`. |
| Approche backend | Cookie `_local_session` distinct + dep unifiée | Sépare explicitement les provenances. Pas de fake-OIDC. |
| Stockage de la config OIDC | DB (table `oidc_config` existante) | Inchangé. Persistant à travers redémarrages. |

## 4. Architecture

### 4.1 Chemins d'authentification après cette feature

```
                Browser → /ui/login
                       │
        ┌──────────────┼──────────────────────┐
        ▼              ▼                      ▼
  ┌──────────┐  ┌──────────────┐     ┌──────────────┐
  │  Bearer  │  │ Session OIDC │     │ Session local│
  │master-key│  │  (Keycloak)  │     │ (bootstrap)  │
  └────┬─────┘  └──────┬───────┘     └──────┬───────┘
       │ agents,       │ via /auth/login    │ via /auth/local/login
       │ curl          │ → Keycloak         │ → POST {username,password}
       └─────┬─────────┴────────────────────┘
             ▼
    require_master_key_or_authenticated_admin
                  (nouvelle dep)
             ▼
       endpoints admin
       (/api/admin/*, /me, OidcConfigPage…)
```

### 4.2 Composants nouveaux

- **Backend** : `LocalAuthService` (vérification hash bcrypt), trois nouvelles
  routes (`/auth/local/login`, `/auth/local/logout`, `/api/auth/methods`),
  dep unifiée `require_master_key_or_authenticated_admin`, extension de `/me`
  pour résoudre la session locale.
- **Frontend** : route React `/ui/login` (page de login unifiée non guardée),
  hook `useAuthMethods`, adaptation `AuthGuard` et `Header`, i18n
  `login.{fr,en}.json`.
- **Script** : extension `dev-deploy.sh` qui initialise
  `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` si vide et affiche le password en clair.

### 4.3 Garanties de sécurité

- Bootstrap actif **uniquement** si `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` est
  non-vide au boot. L'opérateur coupe en retirant la var + redémarrant.
- Le hash bcrypt est seul stocké en `.env` ; le password en clair n'est jamais
  persistant — il transite uniquement par la console de `dev-deploy.sh` au
  moment de la génération initiale.
- Comparaison `bcrypt.checkpw` (constant-time).
- Session locale signée par `SECRET_KEY` du `SessionMiddleware` Starlette
  (mécanisme existant, déjà tamper-resistant).
- TTL fixe (`RAG_BOOTSTRAP_SESSION_TTL_SECONDS`, défaut 8 h). Pas de refresh
  token : à expiration, re-login complet.
- Log structuré `auth.local.login.success` ou `auth.local.login.failure` à
  chaque tentative (incluant l'IP via `request.client.host`). Pas d'autre PII.

## 5. Composants backend

### 5.1 Config (`backend/src/rag/config.py`)

Trois nouveaux champs sur `Settings` (Pydantic) :

```python
rag_bootstrap_admin_password_hash: str = ""   # vide = bootstrap désactivé
rag_bootstrap_admin_username: str = "admin"   # fixe par défaut
rag_bootstrap_session_ttl_seconds: int = 28800  # 8h
```

Property dérivée `bootstrap_enabled: bool` =
`bool(rag_bootstrap_admin_password_hash.strip())`. Pas de validation du format
du hash au boot ; `bcrypt.checkpw` lèvera au premier appel si malformé, et le
service retournera `False` (login échoué).

### 5.2 `LocalAuthService` (nouveau, `backend/src/rag/services/local_auth.py`)

```python
class LocalAuthService:
    def __init__(self, *, username: str, password_hash: str,
                 ttl_seconds: int) -> None: ...

    @property
    def enabled(self) -> bool: ...

    def verify(self, *, username: str, password: str) -> bool:
        """bcrypt.checkpw, constant-time. False si bootstrap désactivé,
        username ne match pas, ou hash invalide."""

    def build_session_payload(self) -> dict:
        """Returns {'username': ..., 'expires_at': now + ttl}."""
```

Instancié dans le lifespan, attaché à `app.state.local_auth`. Pas de pool DB
requis.

### 5.3 Routes backend

Étend `backend/src/rag/api/auth.py` (router existant `/auth`) :

| Méthode | Path | Auth | Body | Réponses |
|---|---|---|---|---|
| POST | `/auth/local/login` | publique | `{username, password}` | 200 `{ok:true}` + cookie ; 401 `invalid_credentials` ; 503 `bootstrap_disabled` ; 422 body invalide |
| POST | `/auth/local/logout` | publique (idempotent) | — | 204 (clear `_local_session` du cookie) |

Nouveau router `/api/auth/methods` (peut vivre dans `auth.py` ou nouveau
fichier `api/auth_public.py`) :

| Méthode | Path | Auth | Réponse |
|---|---|---|---|
| GET | `/api/auth/methods` | publique | `{oidc_configured: bool, bootstrap_enabled: bool}` |

### 5.4 Dep unifiée (`backend/src/rag/auth/bearer.py`)

Nouvelle dep `require_master_key_or_authenticated_admin` :

```
1. Si header Authorization présent → require_master_key
2. Sinon si _local_session dans request.session et expires_at > now → ok
3. Sinon si _local_session dans request.session et expiré → clear + raise
   LocalSessionExpired
4. Sinon → require_oidc_role("rag-admin")
```

Migration des routers admin existants vers cette nouvelle dep :
- `backend/src/rag/api/admin_oidc.py:14` (`build_admin_oidc_router`)
- `backend/src/rag/api/admin_harpocrate_vaults.py` (router CRUD coffres)
- `backend/src/rag/api/admin.py` (`build_admin_router`)

L'ancienne dep `require_master_key_or_oidc_role` reste en place mais n'est
plus utilisée par les routers admin (peut être supprimée dans un jalon
ultérieur si aucun usage subsistant).

### 5.5 `/me` étendu (`backend/src/rag/api/auth.py`)

Résolution dans l'ordre suivant :

```
1. request.session.get("_local_session") :
   - présent + non expiré → return {sub:"admin", email:null, name:null,
                                    roles:["rag-admin"]}
   - présent + expiré → clear + raise LocalSessionExpired
2. request.session.get("_oidc_session") → chemin OIDC existant inchangé
3. ni l'un ni l'autre → raise OidcSessionMissing (sémantique actuelle)
```

### 5.6 Erreurs typées (`backend/src/rag/api/errors.py`)

Trois nouvelles erreurs + handler global :

- `BootstrapDisabled` → 503 `{"error":"bootstrap_disabled","message":"…"}`
- `LocalAuthInvalidCredentials` → 401 `{"error":"invalid_credentials",…}`
  (uniforme : ne distingue pas username inconnu vs mauvais pwd, pour limiter
  l'enumeration).
- `LocalSessionExpired` → 401 `{"error":"local_session_expired",…}` (le
  frontend redirige vers `/ui/login`).

### 5.7 Pas de migration DB

Le bootstrap vit **uniquement en mémoire** (Settings au boot + cookie Starlette
signé). Aucune table, aucune migration SQL. Rotation = modifier `.env` +
redémarrer le backend.

## 6. Composants frontend

### 6.1 Nouvelle route React `/ui/login`

Le routing actuel n'a pas de `/ui/login` — `AuthGuard`
(`frontend/src/components/AuthGuard.tsx:22`) redirige aujourd'hui directement
vers `/auth/login` (backend OIDC). Avec cette feature, AuthGuard redirige vers
`/ui/login?next=...`, et c'est cette nouvelle page React qui décide quoi
afficher selon `GET /api/auth/methods`.

Nouveau fichier : `frontend/src/pages/LoginPage.tsx`, **non guardé** par
`<AuthGuard>` (route définie en dehors).

### 6.2 Hook `useAuthMethods`

`frontend/src/hooks/useAuthMethods.ts` :

```ts
export function useAuthMethods() {
  return useQuery({
    queryKey: ["auth", "methods"],
    queryFn: () => fetch("/api/auth/methods").then(r => r.json()),
    staleTime: Infinity,
  });
}
// returns { oidc_configured: boolean, bootstrap_enabled: boolean }
```

### 6.3 Mockup ASCII des 4 états de `LoginPage`

**État 1 — OIDC configuré + bootstrap actif** (cas nominal après config)

```
+---------------------------------------------+
|              ag-flow.rag                    |
|                                             |
|   +-------------------------------------+   |
|   |  → Connexion via Keycloak           |   |
|   +-------------------------------------+   |
|                                             |
|   --------- ou login admin local ---------  |
|                                             |
|   Username  [admin                    ]     |
|   Password  [.....................    ]     |
|                                             |
|   +-------------------------------------+   |
|   |  Se connecter                       |   |
|   +-------------------------------------+   |
+---------------------------------------------+
```

**État 2 — OIDC pas configuré + bootstrap actif** (premier boot)

```
+---------------------------------------------+
|              ag-flow.rag                    |
|                                             |
|   Login admin (bootstrap)                   |
|                                             |
|   Username  [admin                    ]     |
|   Password  [.....................    ]     |
|                                             |
|   +-------------------------------------+   |
|   |  Se connecter                       |   |
|   +-------------------------------------+   |
|                                             |
|   ! OIDC pas encore configuré. Loguez-vous  |
|     avec le compte admin local pour le      |
|     paramétrer.                             |
+---------------------------------------------+
```

**État 3 — OIDC configuré + bootstrap désactivé** (prod nominale)

```
+---------------------------------------------+
|              ag-flow.rag                    |
|                                             |
|   +-------------------------------------+   |
|   |  → Connexion via Keycloak           |   |
|   +-------------------------------------+   |
+---------------------------------------------+
```

**État 4 — ni l'un ni l'autre** (état dégradé)

Message d'erreur clair : « Aucune méthode d'authentification configurée —
contactez l'administrateur ».

### 6.4 Validation Zod et soumission

```ts
const schema = z.object({
  username: z.string().min(1, "required"),
  password: z.string().min(1, "required"),
});
```

`react-hook-form` + `useMutation` sur `POST /auth/local/login`. Sur succès :
`window.location.href = next || "/ui/workspaces"`. Sur 401 : toast
`t("errors.invalid_credentials")`. Sur 503 `bootstrap_disabled` : refetch
`useAuthMethods` puis bascule de rendu (rare, l'opérateur a coupé bootstrap
pendant la session de login).

### 6.5 i18n

Nouveau namespace `login` dans `frontend/src/i18n/fr/login.json` et
`frontend/src/i18n/en/login.json` :

```json
{
  "title": "Connexion",
  "oidc": { "button": "Connexion via Keycloak" },
  "local": {
    "section_title": "Login admin local",
    "fields": { "username": "Username", "password": "Password" },
    "submit": "Se connecter"
  },
  "errors": {
    "invalid_credentials": "Identifiants invalides",
    "no_method": "Aucune méthode d'authentification configurée",
    "bootstrap_disabled": "Login local désactivé"
  },
  "info": {
    "oidc_not_configured": "OIDC pas encore configuré. Loguez-vous avec le compte admin local pour le paramétrer."
  }
}
```

### 6.6 Adaptation `AuthGuard` et `Header`

`AuthGuard.tsx` : changer le redirect 401 vers `/ui/login?next=...`.

`Header.tsx` : bouton "Déconnexion" choisit l'endpoint selon la nature de la
session — détectée via `useUser()` (du contexte `AuthGuard`) :
- `sub === "admin"` et `email === null` → POST `/auth/local/logout` puis
  `window.location = "/ui/login"`.
- Sinon → comportement OIDC existant (`/auth/logout`).

## 7. Data flow

### 7.1 Login local nominal

```
Browser              Frontend                Backend                  Cookie
   |                       |                       |                     |
   |---GET /ui/----------->|                       |                     |
   |                       |---GET /me------------>|                     |
   |                       |<--401 missing----------                     |
   |<--redirect /ui/login?next=/ui/                                       |
   |---GET /ui/login------>|                       |                     |
   |                       |---GET /api/auth/methods->                   |
   |                       |<--{oidc:false, bootstrap:true}              |
   |  (saisit admin/pwd)   |                       |                     |
   |---submit------------->|---POST /auth/local/login {...}->            |
   |                       |                       | bcrypt.checkpw      |
   |                       |                       | set _local_session  |
   |                       |<--200 + Set-Cookie ---|                     |
   |                       |  window.location = next                     |
   |---GET /ui/----------->|---GET /me------------>|                     |
   |                       |                       | _local_session ok   |
   |                       |<--{sub:"admin",roles:["rag-admin"]}         |
   |  AuthGuard ok, render IHM                                            |
```

### 7.2 Bootstrap → configuration OIDC → coexistence

L'utilisateur loggué via bootstrap accède à `/ui/oidc`. La dep
`require_master_key_or_authenticated_admin` autorise la session locale, donc
`GET /api/admin/oidc` répond 503 `oidc_not_configured` (config absente), le
form s'affiche vide, et le `POST /api/admin/oidc` est accepté avec la session
locale. Après save, `OidcService.upsert_config` (existant,
`services/oidc.py:113-141`) fait DELETE + INSERT en transaction.

L'opérateur peut désormais utiliser SSO. La session locale reste valide
jusqu'à son TTL ; rien n'est révoqué automatiquement.

### 7.3 Résolution `/me` avec session locale (séquentiel)

```
GET /me
  │
  ├─ request.session.get("_local_session") :
  │    ├─ présent et non expiré → return user local
  │    └─ présent mais expiré → clear + LocalSessionExpired (401)
  │
  ├─ sinon : request.session.get("_oidc_session") → chemin OIDC existant
  │
  └─ sinon : OidcSessionMissing (401)
```

### 7.4 Coexistence des deux sessions

Le cookie Starlette est un dict signé pouvant contenir simultanément
`_oidc_session` et `_local_session`. La dep résout dans l'ordre **Bearer →
local → OIDC**. Aucune promotion automatique de session locale vers OIDC :
l'utilisateur fait logout + login SSO manuellement s'il veut basculer.

### 7.5 Cas d'erreur et UX frontend

| Erreur backend | HTTP | UX frontend |
|---|---|---|
| `invalid_credentials` | 401 | Toast erreur, form reste, focus password |
| `bootstrap_disabled` | 503 | Refetch `useAuthMethods`, bascule état rendu |
| `local_session_expired` | 401 | AuthGuard détecte, redirect `/ui/login?next=...` |
| Réseau / 5xx générique | 5xx | Toast erreur générique |

## 8. Tests

### 8.1 Backend (pytest)

`backend/tests/services/test_local_auth.py` — service pur :
- `verify_success`, `verify_wrong_password`, `verify_wrong_username`,
  `verify_when_disabled`, `build_session_payload_has_expiry`.

`backend/tests/api/test_auth_local.py` — endpoints :
- Login succès, login mauvais pwd (401 uniforme), bootstrap désactivé (503),
  body invalide (422), logout idempotent, `/api/auth/methods` sous les 4
  combinaisons.

`backend/tests/auth/test_admin_dep.py` — dep unifiée :
- Bearer ok, session locale ok, session OIDC ok (non-régression), locale
  expirée (401), aucune des trois (401), Bearer invalide prime (préserve la
  sémantique actuelle).

Les tests OIDC utilisent un stub `OidcService` injecté via `app.state.oidc`
(pattern déjà en place dans `tests/`).

### 8.2 Frontend (Vitest + RTL)

`frontend/src/pages/__tests__/LoginPage.test.tsx` :
- Rendu des 4 états selon `useAuthMethods`.
- Submit valide → POST `/auth/local/login`, redirect vers `next`.
- Submit 401 → toast erreur, form reste.
- Submit pendant chargement → bouton disabled.
- Click "Connexion via Keycloak" → `window.location = "/auth/login?next=..."`.

`frontend/src/components/__tests__/AuthGuard.test.tsx` (étend existant) :
- Redirect 401 va vers `/ui/login?next=...`.

`frontend/src/components/__tests__/Header.test.tsx` (étend existant) :
- Session locale → POST `/auth/local/logout`.
- Session OIDC → `/auth/logout` (path existant).

### 8.3 Smoke manuel end-to-end

1. LXC neuf : `./dev-deploy.sh` → noter le password affiché.
2. Ouvrir `http://<ip>/ui/` → redirect `/ui/login` → état 2.
3. Saisir `admin` + password → succès → `/ui/workspaces`.
4. Aller sur `/ui/oidc` → remplir → save → toast success.
5. Logout → re-login local → toujours possible (bootstrap actif).
6. Optionnel : retirer la var du `.env`, redémarrer, re-login local → 503.

## 9. Extension `dev-deploy.sh`

Ajout d'un bloc juste après l'initialisation de `POSTGRES_PASSWORD` (même
pattern, même endroit), avant `docker compose up -d` :

```bash
ensure_bootstrap_admin_hash() {
  local env_file="$1"
  local current
  current=$(grep -E '^RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=' "$env_file" 2>/dev/null \
            | head -1 | cut -d= -f2-)
  if [[ -n "$current" ]]; then
    echo "  ✓ RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH déjà défini"
    return 0
  fi

  local plain hash
  plain=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
  hash=$(openssl passwd -bcrypt "$plain")

  if grep -qE '^RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=' "$env_file"; then
    sed -i "s|^RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=.*|RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=${hash}|" "$env_file"
  else
    echo "RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=${hash}" >> "$env_file"
  fi

  echo
  echo "═══════════════════════════════════════════════════════════"
  echo "  COMPTE ADMIN BOOTSTRAP CRÉÉ"
  echo "  Username : admin"
  echo "  Password : ${plain}"
  echo "  ⚠ Note ce password MAINTENANT, il n'est pas stocké en clair."
  echo "═══════════════════════════════════════════════════════════"
  echo
}

ensure_bootstrap_admin_hash "/opt/rag/.env"
```

Pas de suite de tests bash dans ce jalon (le script n'en a pas aujourd'hui ;
hors-scope d'en introduire une). Validation manuelle au déploiement.

## 10. Plan de livraison (haut niveau)

Estimation 6 tâches TDD, à détailler dans un plan séparé :

- **T1** — `LocalAuthService` + tests purs.
- **T2** — Routes `/auth/local/login|logout` + `/api/auth/methods` + tests
  endpoints.
- **T3** — Dep unifiée `require_master_key_or_authenticated_admin` +
  migration des 3 routers admin + tests dep.
- **T4** — `/me` étendu pour résoudre la session locale + tests.
- **T5** — `LoginPage` React + hook `useAuthMethods` + tests Vitest +
  adaptation `AuthGuard` & `Header` + i18n.
- **T6** — Extension `dev-deploy.sh` + smoke manuel end-to-end documenté.

## 11. Hors-scope explicite

- Aucune table DB ni migration pour cette feature. Rotation = `.env` +
  redémarrer.
- Pas de rate-limit dédié sur `/auth/local/login`. Le délai bcrypt (~250 ms)
  est une protection naturelle ; un rate-limit global pourrait être ajouté
  dans un autre jalon si nécessaire.
- Pas de promotion automatique session locale → OIDC. Logout/relogin manuel.
- Pas de mécanisme de récupération si l'opérateur perd à la fois le password
  et le hash. La solution est de regénérer via `dev-deploy.sh`.
- Pas de support multi-user local. Feature dédiée si besoin un jour (table DB
  + page admin "users locaux").
- L'ancienne dep `require_master_key_or_oidc_role` est laissée en place pour
  ce jalon. Sa suppression éventuelle est un nettoyage ultérieur.

## 12. Risques

| Risque | Mitigation |
|---|---|
| Opérateur oublie de retirer le bootstrap en prod | Doc claire dans `Install-dev.md` ; log structuré à chaque login local pour traçabilité ; rotation password trivialement réversible. |
| `SECRET_KEY` Starlette compromise → cookies forgeables | Risque déjà présent pour les sessions OIDC. Pas spécifique au bootstrap. |
| Hash bcrypt malformé dans `.env` | `LocalAuthService.verify` retourne `False` (login échoué, pas de crash). Pas de validation au boot pour éviter un fail-fast pénible en dev. |
| Énumération de l'admin via timing attack | Réponse 401 uniforme + bcrypt constant-time. L'absence de l'option "username inconnu" différenciée empêche l'énumération. |
| `dev-deploy.sh` exécuté plusieurs fois | Idempotent : si la var est déjà définie, on ne touche pas. Le password n'est affiché qu'à la première exécution. |
