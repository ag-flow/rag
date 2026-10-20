"""Routes du parcours « Connecter à Harpocrate » (création d'un coffre sans
copier-coller de clé). Logique : `rag.services.harpocrate_connect`."""

from __future__ import annotations

from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from rag.api.public_base import public_base_from_request
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.harpocrate_vaults import VaultConnectStartResponse, VaultIdentity
from rag.secrets.exceptions import HarpocrateDekMissingError
from rag.services.harpocrate_connect import ConnectFlowError, HarpocrateConnectService

log = structlog.get_logger(__name__)

# Clé de session (cookie signé Starlette) : n'y vit QUE le jeton de liaison,
# jamais l'état PKCE ni la clé privée — le cookie est signé mais lisible.
_BINDING_KEY = "harpocrate_connect_binding"
_CALLBACK_PATH = "/api/admin/harpocrate-vaults/connect/callback"
# Retour vers l'IHM : chemin fixe, jamais une valeur de la requête (pas de
# redirection ouverte).
_UI_PATH = "/ui/settings/harpocrate-vaults"

router = APIRouter(
    prefix="/api/admin/harpocrate-vaults/connect",
    tags=["admin-harpocrate-vaults"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


def _service(request: Request) -> HarpocrateConnectService:
    svc: HarpocrateConnectService = request.app.state.harpocrate_connect_service
    return svc


def _public_base(request: Request) -> str:
    # Même résolution que le login OIDC : l'URL publique fixée dans l'IHM,
    # sinon l'adresse d'appel. L'URL de retour doit être EXACTEMENT celle
    # déclarée chez Harpocrate, au caractère près.
    base: str = request.app.state.admin_env.get_public_url() or public_base_from_request(request)
    return base.rstrip("/")


@router.post("/start", response_model=VaultConnectStartResponse)
async def start_connect(identity: VaultIdentity, request: Request) -> VaultConnectStartResponse:
    # Le parcours revient par le NAVIGATEUR : il exige une session d'admin
    # pour y lier le state. Un appel par master key n'a pas de session à
    # lier — refus explicite plutôt qu'une liaison vide (fail closed).
    if request.headers.get("Authorization"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "connect_requires_browser_session")
    owner_id = get_current_owner_id(request)
    redirect_uri = f"{_public_base(request)}{_CALLBACK_PATH}"
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            started = await _service(request).resolve_start(
                conn, identity=identity, owner_id=owner_id, redirect_uri=redirect_uri
            )
        except ConnectFlowError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, exc.reason) from exc
        except HarpocrateDekMissingError as exc:
            # Sans DEK, la clé obtenue ne pourrait pas être chiffrée au retour :
            # on refuse AVANT d'envoyer l'admin consentir chez Harpocrate.
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "harpocrate_dek_missing"
            ) from exc
    request.session[_BINDING_KEY] = started.binding_token
    return VaultConnectStartResponse(browser_url=started.browser_url)


@router.get("/callback", include_in_schema=False)
async def connect_callback(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Retour du navigateur depuis Harpocrate : conclut puis renvoie vers l'IHM.

    Le jeton de liaison est retiré de la session quoi qu'il arrive : une
    demande ne se conclut qu'une fois, un retour arrière ne la rejoue pas.
    """
    binding = request.session.pop(_BINDING_KEY, None)
    owner_id = get_current_owner_id(request)
    svc = _service(request)
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            vault = await svc.resolve_callback(
                conn,
                owner_id=owner_id,
                binding_token=binding,
                state=state,
                code=code,
                error=error,
            )
        except ConnectFlowError as exc:
            return _to_ui({"connect_error": exc.reason})
        except HarpocrateDekMissingError:
            return _to_ui({"connect_error": "harpocrate_dek_missing"})
        tested = await request.app.state.harpocrate_vaults_service.test_connection(conn, vault.id)
    log.info("harpocrate_connect.tested", vault_id=str(vault.id), ok=tested.ok)
    return _to_ui({"connect": "ok", "vault": str(vault.id), "tested": str(tested.ok).lower()})


def _to_ui(params: dict[str, str]) -> RedirectResponse:
    return RedirectResponse(
        f"{_UI_PATH}?{urlencode(params)}", status_code=status.HTTP_303_SEE_OTHER
    )
