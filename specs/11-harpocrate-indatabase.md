CHANTIER À REPRODUIRE — « Coffres Harpocrate configurables côté DB »

  CONTEXTE
  Tu travailles sur un module AGFlow autre que `agflow.docker`. Ton module utilise déjà Harpocrate comme coffre de secrets (`vault_client.py`, env vars
  HARPOCRATE_KEY/URL, pattern `${vault://HARPOCRATE_KEY:<path>}` dans les colonnes de tables qui stockent des credentials). Le module `agflow.docker`
  (branche `dev`) vient de remplacer cette config par env var par une table DB `harpocrate_vaults` avec UI dédiée. Objectif : reproduire le même
  refactor chez toi pour avoir une config multi-coffres rotable depuis l'UI, sans toucher au .env.

  RÉFÉRENCE — 4 commits sur agflow.docker/dev qui constituent le chantier :

  | Commit  | Lignes | Périmètre                                                                                              |
  |---------|--------|--------------------------------------------------------------------------------------------------------|
  | 8681c3b | +1252 / -218 sur 18 fichiers | Backend complet : migration SQL, schémas Pydantic, service vaults, API admin 6 endpoints, refactor
  `vault_client` multi-coffres, adaptation des 3 services métier qui stockaient déjà des secrets vault. |
  | 6cff9c6 | +584   sur  9 fichiers | Frontend : page `/settings` avec Tabs, onglet « Harpocrate », hook React Query, api client, i18n FR/EN,
  désactivation conditionnelle du bouton « Nouveau secret vault » sur la page Secrets. |
  | cee6664 | +67 / -58 sur 2 fichiers | Fix tests : adaptation au nouveau contrat `vault_client` (kwarg `vault_name`, refs avec nom logique du coffre,
  mock `harpocrate_vaults_service.get_default`). |
  | aa35072 | +3 / -3 sur 1 fichier | Fix tests : pattern d'assertion sur `r.text` trop large (`"api_key"` matche `"api_key_id"`). |

  OBJECTIF DE CETTE TÂCHE
  Reproduire les commits 1 à 3 dans ton module, adaptés à ta liste de services métier qui stockent des secrets vault. Le commit 4 est juste un fix
  d'erreur de copie : à éviter dès le début, voir « Pièges » plus bas.

  ══════════════════════════════════════════════════════════════════════════════
  COMMIT 1 — Backend complet (1252 lignes ajoutées)
  ══════════════════════════════════════════════════════════════════════════════

  ### 1.1 Migration SQL — `backend/migrations/<num>_harpocrate_vaults.sql`

  Prends le prochain numéro libre dans `backend/migrations/`. Pré-requis : extension `pgcrypto` déjà activée (sinon ajoute `CREATE EXTENSION IF NOT
  EXISTS pgcrypto;` au début). La fonction `set_updated_at()` doit déjà exister (sinon copie-la du `001_init.sql` d'agflow.docker).

  ```sql
  CREATE TABLE IF NOT EXISTS harpocrate_vaults (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      name varchar NOT NULL UNIQUE,
      base_url varchar NOT NULL,
      api_key_id varchar NOT NULL,
      api_key_encrypted bytea NOT NULL,
      is_default boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
  );

  -- Un seul coffre default à la fois (partial unique index)
  CREATE UNIQUE INDEX IF NOT EXISTS harpocrate_vaults_default_unique
      ON harpocrate_vaults (is_default) WHERE is_default;

  DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_harpocrate_vaults_updated_at') THEN
          CREATE TRIGGER trg_harpocrate_vaults_updated_at
              BEFORE UPDATE ON harpocrate_vaults
              FOR EACH ROW EXECUTE FUNCTION set_updated_at();
      END IF;
  END $$;

  1.2 Nouvelle env var HARPOCRATE_DEK

  C'est la passphrase pgcrypto qui chiffre la colonne api_key_encrypted. Ne JAMAIS la régénérer (ou rotate via re-chiffrement explicite). Génération
  initiale : python -c "import secrets; print(secrets.token_urlsafe(48))".

  - backend/src/agflow/config.py — ajoute harpocrate_dek: str = "" à la classe Settings.
  - .env.example — ajoute la variable avec un commentaire explicatif.
  - Script de bootstrap deploy (si tu en as un, ex: dev-deploy.sh) — génère la valeur au premier passage et l'écrit dans .env.

  1.3 Schémas Pydantic — backend/src/agflow/schemas/harpocrate_vaults.py

  from __future__ import annotations
  from datetime import datetime
  from uuid import UUID
  from pydantic import BaseModel, ConfigDict, Field, HttpUrl

  class VaultSummary(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      id: UUID
      name: str
      base_url: str  # str et pas HttpUrl en sortie (évite la normalisation trailing slash)
      api_key_id: str
      is_default: bool
      created_at: datetime
      updated_at: datetime

  class VaultCreateRequest(BaseModel):
      name: str = Field(min_length=1, max_length=128)
      base_url: HttpUrl                    # validation côté input
      api_key_id: str = Field(min_length=1, max_length=128)
      api_key: str = Field(min_length=1)
      is_default: bool = False

  class VaultUpdateRequest(BaseModel):
      name: str | None = Field(default=None, min_length=1, max_length=128)
      base_url: HttpUrl | None = None
      api_key_id: str | None = Field(default=None, min_length=1, max_length=128)
      api_key: str | None = Field(default=None, min_length=1)
      is_default: bool | None = None

  class VaultTestConnectionResult(BaseModel):
      ok: bool
      error: str | None = None

  ATTENTION : VaultSummary.base_url doit être str, pas HttpUrl. Sinon Pydantic v2 ajoute un / trailing à la sérialisation et tes tests qui comparent une
   URL exacte foirent.

  1.4 Service — backend/src/agflow/services/harpocrate_vaults_service.py

  API publique du module (à respecter pour que vault_client puisse lookup) :

  list_all() -> list[VaultSummary]
  get_by_id(vault_id) -> VaultSummary           # raise VaultNotFoundError
  get_by_name(name) -> VaultSummary | None
  get_default() -> VaultSummary | None
  reveal_api_key(vault_id) -> str               # internal-only, JAMAIS dans une réponse HTTP
  create(payload) -> VaultSummary               # raise DuplicateVaultNameError / NoDekConfiguredError
  update(vault_id, payload) -> VaultSummary     # rotation api_key si fourni
  delete(vault_id)                              # raise VaultNotFoundError
  set_default(vault_id) -> VaultSummary         # transaction atomique
  test_connection(vault_id) -> VaultTestConnectionResult  # whoami() SDK

  Détails d'implémentation critiques :

  - Chiffrement : PGP_SYM_ENCRYPT($value, $dek) et PGP_SYM_DECRYPT(col, $dek). Le DEK vient de get_settings().harpocrate_dek. Si vide →
  NoDekConfiguredError.
  - Bascule du flag is_default : opération en transaction (pool.acquire() ... conn.transaction()). Avant INSERT ... is_default=true ou UPDATE ...
  is_default=true, faire UPDATE harpocrate_vaults SET is_default=false WHERE is_default=true [AND id != $1] pour éviter la violation du partial unique
  index.
  - test_connection : appelle harpocrate.VaultClient(token=key, base_url=url).whoami() dans un asyncio.to_thread. Tronque l'erreur à 200 chars dans la
  réponse HTTP pour éviter de leak des détails sensibles.
  - Logs : ne JAMAIS logger la valeur de api_key ni le résultat de reveal_api_key. Logger uniquement vault_id, name, is_default.

  3 exceptions à définir dans le module : VaultNotFoundError, DuplicateVaultNameError, NoDekConfiguredError.

  1.5 Router admin — backend/src/agflow/api/admin/harpocrate_vaults.py

  6 endpoints, tous sous require_admin :

  ┌─────────┬───────────────────────────────────────────────────┬───────────────┬───────────────────────────────────────────────────────┐
  │ Méthode │                       Path                        │    Réponse    │                    Codes d'erreur                     │
  ├─────────┼───────────────────────────────────────────────────┼───────────────┼───────────────────────────────────────────────────────┤
  │ GET     │ /api/admin/harpocrate-vaults                      │ list[Summary] │ 401/403                                               │
  ├─────────┼───────────────────────────────────────────────────┼───────────────┼───────────────────────────────────────────────────────┤
  │ POST    │ /api/admin/harpocrate-vaults                      │ 201 + Summary │ 409 DuplicateVaultNameError, 503 NoDekConfiguredError │
  ├─────────┼───────────────────────────────────────────────────┼───────────────┼───────────────────────────────────────────────────────┤
  │ PUT     │ /api/admin/harpocrate-vaults/{id}                 │ 200 + Summary │ 404, 409, 503                                         │
  ├─────────┼───────────────────────────────────────────────────┼───────────────┼───────────────────────────────────────────────────────┤
  │ DELETE  │ /api/admin/harpocrate-vaults/{id}                 │ 204           │ 404                                                   │
  ├─────────┼───────────────────────────────────────────────────┼───────────────┼───────────────────────────────────────────────────────┤
  │ POST    │ /api/admin/harpocrate-vaults/{id}/set-default     │ 200 + Summary │ 404                                                   │
  ├─────────┼───────────────────────────────────────────────────┼───────────────┼───────────────────────────────────────────────────────┤
  │ POST    │ /api/admin/harpocrate-vaults/{id}/test-connection │ 200 + Result  │ 404                                                   │
  └─────────┴───────────────────────────────────────────────────┴───────────────┴───────────────────────────────────────────────────────┘

  Inclure dans main.py :
  from agflow.api.admin.harpocrate_vaults import router as admin_harpocrate_vaults_router
  ...
  app.include_router(admin_harpocrate_vaults_router)

  Et brancher la nouvelle erreur sur l'endpoint de création de secret vault existant chez toi (/api/admin/secrets/vault ou équivalent) :
  except vault_client.VaultNotFoundError as exc:
      raise HTTPException(status_code=503, detail=str(exc)) from exc

  1.6 Refactor vault_client.py — multi-coffres avec cache par nom

  Tout module qui utilise actuellement vault_client.get_secret(path) continue de fonctionner (résolution implicite du coffre default), mais l'API gagne
  un kwarg vault_name et trois helpers.

  # Nouvelles fonctions publiques :
  def parse_ref(value: str | None) -> tuple[str, str] | None       # extrait (vault_name, path)
  def build_ref(vault_name: str, path: str) -> str                  # construit ${vault://name:path}
  async def resolve_ref(ref: str) -> str                            # parse + route + fetch
  def reset_cache(vault_name: str | None = None) -> None            # invalide cache

  # Les fonctions existantes gagnent un kwarg vault_name=None :
  async def get_secret(name: str, vault_name: str | None = None) -> str
  async def create_secret(name, value, description=None, vault_name=None) -> str
  async def update_secret(name, value, vault_name=None) -> None
  async def delete_secret(name, vault_name=None) -> None
  async def list_secrets(limit=200, vault_name=None) -> list

  # Exceptions :
  class VaultNotFoundError(Exception): ...
  class InvalidVaultRefError(Exception): ...

  Logique interne :
  - _clients: dict[str, VaultClient] — cache par nom de coffre.
  - _resolve_vault_credentials(vault_name) :
    - Si vault_name est None : harpocrate_vaults_service.get_default(). Si None aussi, fallback sur settings.harpocrate_key + settings.harpocrate_url
  (compat bootstrap), sinon VaultNotFoundError.
    - Si vault_name fourni : harpocrate_vaults_service.get_by_name(vault_name). Si None, VaultNotFoundError.
  - _ensure_client(vault_name) : résout les credentials, instancie ou réutilise un VaultClient, cache.
  - Sur VaultHttpError(status_code=401) : reset_cache(name) puis 1 retry. Idem qu'avant mais par-coffre.

  1.7 Adapter tes services métier qui stockent des secrets vault

  Pour chaque service qui stockait ${vault://HARPOCRATE_KEY:<path>} :

  1. Supprime la constante locale _VAULT_KEY_NAME = "HARPOCRATE_KEY", les regex _VAULT_REF_RE, et les helpers _vault_path, _vault_ref, _parse_vault_ref.
  2. Importe harpocrate_vaults_service et vault_client.
  3. Ajoute un helper :
  async def _require_default_vault_name() -> str:
      default = await harpocrate_vaults_service.get_default()
      if default is None:
          raise vault_client.VaultNotFoundError(
              "No default Harpocrate vault configured — see /settings"
          )
      return default.name
  4. Sur les create() :
  vault_name = await _require_default_vault_name()
  await vault_client.create_secret(path, value, vault_name=vault_name)
  ref = vault_client.build_ref(vault_name, path)   # à stocker en DB
  5. Sur les lectures : remplace les anciens vault_client.get_secret(_parse_vault_ref(value)) par vault_client.resolve_ref(value) qui sait router seul.
  6. Sur les update() qui peuvent rotater le secret : vault_client.parse_ref(existing_ref) pour extraire le coffre d'origine et y appliquer la rotation
  (update_secret(path, new_value, vault_name=existing_vault)).
  7. Sur les delete() : vault_client.parse_ref(existing_ref) pour extraire (vault_name, path) et appeler delete_secret(path, vault_name=vault_name). NE
  PAS appeler avec vault_name=None (le default actuel peut être différent du coffre où ce secret a été écrit).

  Pour agflow.docker, ça concernait 3 services : infra_machines_service, infra_certificates_service, infra_swarm_clusters_service. Identifie chez toi
  les équivalents.

  1.8 Tests backend (à reproduire intégralement, ~38 cas)

  - tests/test_harpocrate_vaults_service.py (12 tests intégration DB) : round-trip pgcrypto, set_default atomique, dup name, NoDekConfigured (avec
  monkeypatch.setenv("HARPOCRATE_DEK", "") — voir Piège #2), rotation api_key.
  - tests/test_harpocrate_vaults_endpoint.py (11 tests intégration HTTP) : auth, viewer rejeté, 409, 503, mocks via
  patch("agflow.api.admin.harpocrate_vaults.vaults.list_all", AsyncMock(...)).
  - tests/test_vault_client_refs.py (7 tests purs) : parse_ref valide / invalide, build_ref, round-trip, accepts any vault name.
  - Adapter tests/_vault_mock.py : les 5 fonctions mock acceptent un kwarg vault_name: str | None = None, ajouter _resolve_ref qui utilise
  vault_client.parse_ref + store, patcher _build_vault_client au lieu de _build_client/_sync_client, vault_client._clients.clear().
  - Adapter tes tests existants de services métier qui mockaient vault_client.create_secret(path, value) : ils doivent maintenant attendre le kwarg
  vault_name, et le ref attendu en DB est ${vault://default:...} (ou le nom du coffre que tu décides). Et mocker harpocrate_vaults_service.get_default
  pour retourner un SimpleNamespace(name="default").

  ══════════════════════════════════════════════════════════════════════════════
  COMMIT 2 — Frontend (584 lignes)
  ══════════════════════════════════════════════════════════════════════════════

  2.1 API client — frontend/src/lib/harpocrateVaultsApi.ts

  export interface HarpocrateVaultSummary { id, name, base_url, api_key_id, is_default, created_at, updated_at }
  export interface CreateVaultPayload { name, base_url, api_key_id, api_key, is_default? }
  export interface UpdateVaultPayload { name?, base_url?, api_key_id?, api_key?, is_default? }
  export interface TestConnectionResult { ok, error }

  export const harpocrateVaultsApi = {
    list, create, update, remove, setDefault, testConnection
  };

  2.2 Hook React Query — frontend/src/hooks/useHarpocrateVaults.ts

  export function useHarpocrateVaults() {
    // useQuery + useMutation pour create / update / remove / setDefault
    const listQuery = useQuery(["harpocrate-vaults"], () => harpocrateVaultsApi.list());
    const defaultVault = listQuery.data?.find((v) => v.is_default);
    return { vaults, defaultVault, isLoading, error, create, update, remove, setDefault };
  }

  2.3 Page /settings — frontend/src/pages/SettingsPage.tsx

  Layout Tabs shadcn, un seul onglet « Harpocrate » pour l'instant. Structure ouverte pour ajouter d'autres onglets plus tard.

  2.4 Composant onglet — frontend/src/components/settings/HarpocrateVaultsTab.tsx

  Tableau (nom, URL, api_key_id, default badge/bouton, actions), dialog create/edit (Label + Input + Switch/checkbox pour is_default, Input password
  pour api_key), boutons set-default + test-connection (Plug icon) + edit + delete confirm. L'api_key n'est jamais affichée. En édition, le champ
  api_key est optionnel : laisser vide pour ne pas rotater.

  2.5 Routing + sidebar

  - App.tsx : ajoute la route /settings derrière ProtectedRoute.
  - Sidebar.tsx : ajoute une nouvelle section « Paramètres » (admin only), entrée /settings avec icône Settings de lucide-react.

  2.6 i18n FR + EN (~36 clés chacune)

  Sous settings.harpocrate.* : title, add, empty, col_name, col_url, col_api_key_id, col_default, is_default, set_default, test_connection,
  test_ok/test_failed, create_title/edit_title, api_key/api_key_optional/api_key_required, created/updated/deleted, default_set,
  delete_title/delete_description.

  Sous secrets.* (page Secrets existante) : no_vault_configured, no_vault_link.

  2.7 Page Secrets — désactiver le bouton vault si pas de coffre

  const { defaultVault, isLoading: vaultsLoading } = useHarpocrateVaults();
  const noDefaultVault = !vaultsLoading && !defaultVault;

  <Button disabled={formMode !== null || noDefaultVault} ...>
    {t("secrets.add_vault_button")}
  </Button>

  {noDefaultVault && (
    <div className="banner-amber">
      {t("secrets.no_vault_configured")}{" "}
      <Link to="/settings">{t("secrets.no_vault_link")}</Link>
    </div>
  )}

  ══════════════════════════════════════════════════════════════════════════════
  COMMIT 3 — Fix tests services métier (67 lignes)
  ══════════════════════════════════════════════════════════════════════════════

  Si tes services métier avaient déjà des tests qui mockaient vault_client.create_secret(path, value) sans kwarg vault_name, ils vont casser. Les
  adapter :

  from unittest.mock import AsyncMock, patch
  from types import SimpleNamespace

  _VAULT_NAME = "default"

  def _patch_default_vault():
      fake = SimpleNamespace(id=uuid.uuid4(), name=_VAULT_NAME)
      return patch(
          "agflow.services.<your_module>.harpocrate_vaults_service.get_default",
          AsyncMock(return_value=fake),
      )

  async def test_create_stores_vault_ref():
      with (
          _patch_default_vault(),
          patch("agflow.services.<your_module>.vault_client.create_secret") as mock_create,
          ...,
      ):
          # ...
          mock_create.assert_called_once_with(path, value, vault_name=_VAULT_NAME)
          # Vérifie que ce qui est écrit en DB est `${vault://default:<path>}`

  ══════════════════════════════════════════════════════════════════════════════
  PIÈGES CONNUS (apprendre des erreurs)
  ══════════════════════════════════════════════════════════════════════════════

  1. Colonnes secret NOT NULL : si ta DB a private_key NOT NULL, l'approche « INSERT vide puis UPDATE avec ref » échoue. Solution : générer l'UUID en
  Python avant tout I/O, push dans Harpocrate, puis un seul INSERT avec id + refs déjà construits. Rollback si l'INSERT échoue.
  2. monkeypatch.setattr("agflow.config.get_settings", ...) ne marche pas si les services font from agflow.config import get_settings au top. Le
  get_settings du service est une référence locale qui n'est pas affectée. À la place : monkeypatch.setenv("HARPOCRATE_DEK", "") — get_settings() re-lit
   l'env à chaque appel.
  3. Assertion "api_key" not in r.text est trop large : elle matche "api_key_id". Utiliser '"api_key":' not in r.text (avec guillemets autour de la clé
  JSON canonique) + "api_key_encrypted" not in r.text.
  4. docker compose interpole $<lettre> dans les valeurs des env_file:. Si la passphrase HARPOCRATE_DEK contient un $, doubler en $$. C'est le même
  piège que pour les hashes bcrypt commençant par $2b$....
  5. Bug SDK Harpocrate sur les noms path-style (a/b/c) : SecretsClient._resolve_id_if_pathstyle plante avec TypeError: VaultHttpClient.get() got
  multiple values for argument 'path'. Affecte get/update/delete d'un secret dont le nom contient des /. Write (create) marche, list aussi. Fix côté SDK
   Harpocrate upstream (non disponible au moment de ce chantier). Tant que le SDK n'est pas patché, les resolve_ref(...) sur paths hiérarchiques
  plantent → secrets orphelins après DELETE. Documente cette limite dans ton module.
  6. Rétrocompat bootstrap : tant que settings.harpocrate_key + harpocrate_url sont set ET aucun coffre en DB, le fallback s'active automatiquement (cf.
   _resolve_vault_credentials(None)). Tes déploiements existants continuent de fonctionner sans intervention. Dès qu'un coffre est créé via UI, le
  fallback est ignoré. Documente clairement la migration en commentaire dans .env.example.

  ══════════════════════════════════════════════════════════════════════════════
  VALIDATION
  ══════════════════════════════════════════════════════════════════════════════

  Suis ta procédure de test d'intégration habituelle (chez agflow.docker c'est ./scripts/run-test.sh qui crée un LXC neuf et joue 8 assertions incluant
  la suite pytest complète dans le container). Si tu n'as pas l'équivalent, au minimum :

  1. Pytest complet vert (incluant les ~30 nouveaux tests : 12 service + 11 endpoint + 7 helpers + N adaptés sur tes services métier).
  2. Boot lifespan OK avec DB vide ET harpocrate_key/url placeholder (hrpv_1_REPLACE_ME) → pas de crash, le fallback bootstrap est lazy.
  3. Smoke E2E via API authentifié (forge un JWT admin avec ta clé JWT_SECRET) :
    - POST /api/admin/harpocrate-vaults avec un vrai token Harpocrate → 201.
    - POST /…/{id}/test-connection → ok: true.
    - POST /api/admin/secrets/vault (existant) → 201 (au lieu de 503 quand il n'y avait pas de coffre).
  4. UI : naviguer sur /settings, créer un coffre via le dialog, vérifier que le bouton « Nouveau secret vault » sur /secrets redevient cliquable.

  ══════════════════════════════════════════════════════════════════════════════
  RÉCAP RAPIDE DES FICHIERS À TOUCHER CHEZ TOI
  ══════════════════════════════════════════════════════════════════════════════

  Backend (15-18 fichiers selon le nombre de services métier que tu adaptes) :
  - 1 migration SQL (table + index + trigger)
  - 3 fichiers nouveaux : schemas/harpocrate_vaults.py, services/harpocrate_vaults_service.py, api/admin/harpocrate_vaults.py
  - 1 fichier nouveau de test : test_harpocrate_vaults_service.py + test_harpocrate_vaults_endpoint.py + test_vault_client_refs.py
  - 1 modif : services/vault_client.py (refactor multi-coffres)
  - 1 modif : config.py (HARPOCRATE_DEK)
  - 1 modif : main.py (include_router)
  - 1 modif : api/admin/secrets.py (503 si pas de coffre)
  - 1 modif : tests/_vault_mock.py
  - N modifs : tes services métier qui stockent des secrets vault (+ leurs tests)
  - 1 modif : .env.example
  - 1 modif : ton script de bootstrap deploy (génération du DEK)

  Frontend (8-9 fichiers) :
  - 5 fichiers nouveaux : pages/SettingsPage.tsx, components/settings/HarpocrateVaultsTab.tsx, hooks/useHarpocrateVaults.ts, lib/harpocrateVaultsApi.ts
  (+ traduction des clés i18n nouvelle section)
  - 3 modifs : App.tsx (route), Sidebar.tsx (entrée), SecretsPage.tsx (disable bouton + banner)
  - 2 modifs : i18n/fr.json + en.json

  Compose : AUCUNE modification. Pas de mount volumetric, pas de remap, rien.

  Tu peux ouvrir les 4 commits réference dans agflow.docker pour t'inspirer ligne par ligne :
  - 8681c3b : git show 8681c3b
  - 6cff9c6 : git show 6cff9c6
  - cee6664 : git show cee6664
  - aa35072 : git show aa35072