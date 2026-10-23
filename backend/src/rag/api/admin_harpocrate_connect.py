"""Routes du parcours « Connecter à Harpocrate » : création d'un coffre, ou
remplacement de sa clé (« Reconnecter »), sans copier-coller de clé.
Logique : `rag.services.harpocrate_connect` et `harpocrate_reconnect`."""

from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from rag.api.admin_harpocrate_vaults import _check_vault_access
from rag.api.public_base import public_base_from_request
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.harpocrate_vaults import (
    VaultConnectStartResponse,
    VaultIdentity,
    VaultReconnectConfirmResponse,
    VaultReconnectPending,
)
from rag.secrets.exceptions import HarpocrateDekMissingError
from rag.services.harpocrate_connect import ConnectStart, HarpocrateConnectService
from rag.services.harpocrate_connect_common import ConnectFlowError, ConnectOutcome

log = structlog.get_logger(__name__)

# Clé de session (cookie signé Starlette) : n'y vit QUE le jeton de liaison,
# jamais l'état PKCE ni la clé privée — le cookie est signé mais lisible.
_BINDING_KEY = "harpocrate_connect_binding"
# Second jeton, posé au retour d'une reconnexion qui change de wallet : seule
# cette session peut confirmer ou refuser l'enregistrement de la clé obtenue.
_CONFIRM_KEY = "harpocrate_reconnect_confirm"
_CALLBACK_PATH = "/api/admin/harpocrate-vaults/connect/callback"
# Retour vers l'IHM : chemin fixe, jamais une valeur de la requête (pas de
# redirection ouverte).
_UI_PATH = "/ui/settings/harpocrate-vaults"
_DECLARATION_REASONS = frozenset({"client_not_declared", "redirect_uri_not_declared"})

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


def _require_browser_session(request: Request) -> None:
    # Le parcours revient par le NAVIGATEUR : il exige une session d'admin
    # pour y lier le state. Un appel par master key n'a pas de session à
    # lier — refus explicite plutôt qu'une liaison vide (fail closed).
    if request.headers.get("Authorization"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "connect_requires_browser_session")


def _start_refused(exc: ConnectFlowError, request: Request, redirect_uri: str) -> HTTPException:
    if exc.reason in _DECLARATION_REASONS:
        # Valeurs publiques (aucun secret) : ce qu'il faut déclarer chez
        # Harpocrate, au caractère près — sans elles l'admin devine.
        detail: object = {
            "reason": exc.reason,
            "client_id": request.app.state.settings.harpocrate_connect_client_id,
            "redirect_uri": redirect_uri,
        }
        return HTTPException(status.HTTP_409_CONFLICT, detail)
    return HTTPException(status.HTTP_409_CONFLICT, exc.reason)


def _dek_missing(exc: HarpocrateDekMissingError) -> HTTPException:
    # Sans DEK, la clé obtenue ne pourrait pas être chiffrée au retour :
    # on refuse AVANT d'envoyer l'admin consentir chez Harpocrate.
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "harpocrate_dek_missing")


@router.post("/start", response_model=VaultConnectStartResponse)
async def start_connect(identity: VaultIdentity, request: Request) -> VaultConnectStartResponse:
    _require_browser_session(request)
    owner_id = get_current_owner_id(request)
    redirect_uri = f"{_public_base(request)}{_CALLBACK_PATH}"
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            started = await _service(request).resolve_start(
                conn, identity=identity, owner_id=owner_id, redirect_uri=redirect_uri
            )
        except ConnectFlowError as exc:
            raise _start_refused(exc, request, redirect_uri) from exc
        except HarpocrateDekMissingError as exc:
            raise _dek_missing(exc) from exc
    return _browser_departure(request, started)


@router.post("/reconnect/{vault_id}/start", response_model=VaultConnectStartResponse)
async def start_reconnect(vault_id: UUID, request: Request) -> VaultConnectStartResponse:
    """« Reconnecter » : même parcours, la clé obtenue remplacera celle du coffre."""
    _require_browser_session(request)
    owner_id = get_current_owner_id(request)
    redirect_uri = f"{_public_base(request)}{_CALLBACK_PATH}"
    async with request.app.state.pools.config_pool.acquire() as conn:
        vault = await request.app.state.harpocrate_vaults_service.get_by_id(conn, vault_id)
        if vault is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
        # Mêmes droits que « Remplacer la clé » : propriétaire, ou tout admin
        # pour le coffre par défaut.
        _check_vault_access(vault, owner_id)
        try:
            started = await _service(request).resolve_reconnect_start(
                conn, vault=vault, owner_id=owner_id, redirect_uri=redirect_uri
            )
        except ConnectFlowError as exc:
            raise _start_refused(exc, request, redirect_uri) from exc
        except HarpocrateDekMissingError as exc:
            raise _dek_missing(exc) from exc
    return _browser_departure(request, started)


def _browser_departure(request: Request, started: ConnectStart) -> VaultConnectStartResponse:
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
            outcome = await svc.resolve_callback(
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
        if outcome.kind == "confirm_wallet":
            return _ask_wallet_confirmation(request, outcome)
        tested = await request.app.state.harpocrate_vaults_service.test_connection(
            conn, outcome.vault.id
        )
    vault_id = str(outcome.vault.id)
    log.info("harpocrate_connect.tested", vault_id=vault_id, ok=tested.ok)
    result = "ok" if outcome.kind == "created" else "reconnected"
    return _to_ui({"connect": result, "vault": vault_id, "tested": str(tested.ok).lower()})


def _ask_wallet_confirmation(request: Request, outcome: ConnectOutcome) -> RedirectResponse:
    # L'identifiant de la demande va dans l'URL (il n'est pas une preuve) ;
    # le jeton qui autorise la décision reste dans la session.
    request.session[_CONFIRM_KEY] = outcome.confirm_token
    return _to_ui(
        {
            "connect": "confirm_wallet",
            "vault": str(outcome.vault.id),
            "request": str(outcome.pending_request_id),
        }
    )


@router.get("/pending/{request_id}", response_model=VaultReconnectPending)
async def get_pending_reconnect(request_id: UUID, request: Request) -> VaultReconnectPending:
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            return await _service(request).reconnect.db_get_pending(
                conn,
                request_id=request_id,
                confirm_token=request.session.get(_CONFIRM_KEY),
                owner_id=get_current_owner_id(request),
            )
        except ConnectFlowError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, exc.reason) from exc


@router.post("/pending/{request_id}/confirm", response_model=VaultReconnectConfirmResponse)
async def confirm_reconnect(request_id: UUID, request: Request) -> VaultReconnectConfirmResponse:
    """Changement de wallet confirmé : la clé obtenue remplace l'ancienne."""
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            vault = await _service(request).reconnect.resolve_confirm(
                conn,
                request_id=request_id,
                confirm_token=request.session.get(_CONFIRM_KEY),
                owner_id=get_current_owner_id(request),
            )
        except ConnectFlowError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, exc.reason) from exc
        except HarpocrateDekMissingError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "harpocrate_dek_missing"
            ) from exc
        request.session.pop(_CONFIRM_KEY, None)
        tested = await request.app.state.harpocrate_vaults_service.test_connection(conn, vault.id)
    log.info("harpocrate_connect.tested", vault_id=str(vault.id), ok=tested.ok)
    return VaultReconnectConfirmResponse(vault=vault, tested=tested.ok)


@router.post(
    "/pending/{request_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def cancel_reconnect(request_id: UUID, request: Request) -> Response:
    """Changement de wallet refusé : rien ne change, l'ancienne clé reste."""
    async with request.app.state.pools.config_pool.acquire() as conn:
        try:
            await _service(request).reconnect.resolve_cancel(
                conn,
                request_id=request_id,
                confirm_token=request.session.get(_CONFIRM_KEY),
                owner_id=get_current_owner_id(request),
            )
        except ConnectFlowError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, exc.reason) from exc
        except HarpocrateDekMissingError as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "harpocrate_dek_missing"
            ) from exc
    request.session.pop(_CONFIRM_KEY, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _to_ui(params: dict[str, str]) -> RedirectResponse:
    return RedirectResponse(
        f"{_UI_PATH}?{urlencode(params)}", status_code=status.HTTP_303_SEE_OTHER
    )
