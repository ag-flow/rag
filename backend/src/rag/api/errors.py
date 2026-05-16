from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AdminError(Exception):
    """Base des exceptions métier de l'API admin.

    Sous-classées par cas spécifique. Chaque sous-classe définit
    `http_status` et `to_payload()` pour la sérialisation JSON.
    """

    http_status: int = 500

    def to_payload(self) -> dict[str, object]:
        raise NotImplementedError


class WorkspaceNotFound(AdminError):
    http_status = 404

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def to_payload(self) -> dict[str, object]:
        return {"error": "workspace_not_found", "name": self.name}


class WorkspaceAlreadyExists(AdminError):
    http_status = 409

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def to_payload(self) -> dict[str, object]:
        return {"error": "workspace_already_exists", "name": self.name}


class ModelNotSupported(AdminError):
    http_status = 422

    def __init__(
        self,
        provider: str,
        model: str,
        supported: Sequence[tuple[str, str]],
    ) -> None:
        super().__init__(provider, model)
        self.provider = provider
        self.model = model
        self.supported = list(supported)

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "model_not_supported",
            "provider": self.provider,
            "model": self.model,
            "supported": [[p, m] for (p, m) in self.supported],
        }


class RefNotFoundInVault(AdminError):
    http_status = 422

    def __init__(self, ref: str) -> None:
        super().__init__(ref)
        self.ref = ref

    def to_payload(self) -> dict[str, object]:
        return {"error": "ref_not_found_in_vault", "ref": self.ref}


class VaultUnreachable(AdminError):
    http_status = 503

    def to_payload(self) -> dict[str, object]:
        return {"error": "vault_unreachable"}


class IndexerChangeRequiresReindex(AdminError):
    http_status = 409

    def __init__(
        self, *, workspace: str, current: str, requested: str, documents_count: int
    ) -> None:
        super().__init__(workspace)
        self.workspace = workspace
        self.current = current
        self.requested = requested
        self.documents_count = documents_count

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "indexer_change_requires_reindex",
            "current": self.current,
            "requested": self.requested,
            "documents_count": self.documents_count,
            "action": f"POST /workspaces/{self.workspace}/reindex?confirm=true",
        }


class SourceNotFound(AdminError):
    http_status = 404

    def __init__(self, source_id: str) -> None:
        super().__init__(source_id)
        self.source_id = source_id

    def to_payload(self) -> dict[str, object]:
        return {"error": "source_not_found", "id": self.source_id}


class SourceTypeNotSupported(AdminError):
    http_status = 422

    def __init__(self, type_: str) -> None:
        super().__init__(type_)
        self.type = type_

    def to_payload(self) -> dict[str, object]:
        return {"error": "source_type_not_supported", "type": self.type, "supported": ["git"]}


class ModelInUse(AdminError):
    http_status = 409

    def __init__(self, provider: str, model: str, workspaces: Sequence[str]) -> None:
        super().__init__(provider, model)
        self.provider = provider
        self.model = model
        self.workspaces = list(workspaces)

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "model_in_use",
            "provider": self.provider,
            "model": self.model,
            "workspaces": self.workspaces,
        }


class PatchFieldNotAllowed(AdminError):
    http_status = 422

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field

    def to_payload(self) -> dict[str, object]:
        return {"error": "patch_field_not_allowed", "field": self.field}


class InvalidPath(AdminError):
    http_status = 422

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {"error": "invalid_path", "reason": self.reason}


class ContentTooLarge(AdminError):
    http_status = 413

    _LIMIT_BYTES = 5 * 1024 * 1024

    def to_payload(self) -> dict[str, object]:
        return {"error": "content_too_large", "limit_bytes": self._LIMIT_BYTES}


class EmbeddingProviderUnavailable(AdminError):
    http_status = 502

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(provider, reason)
        self.provider = provider
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "embedding_provider_error",
            "provider": self.provider,
            "reason": self.reason,
        }


class OidcNotConfigured(AdminError):
    http_status = 503

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "oidc_not_configured",
            "message": "POST /admin/oidc avec la master-key pour configurer Keycloak",
        }


class OidcKeycloakUnreachable(AdminError):
    http_status = 503

    def __init__(self, issuer: str) -> None:
        super().__init__(issuer)
        self.issuer = issuer

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_keycloak_unreachable", "issuer": self.issuer}


class OidcStateMissing(AdminError):
    http_status = 400

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_state_missing"}


class OidcStateMismatch(AdminError):
    http_status = 400

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_state_mismatch"}


class OidcInvalidCode(AdminError):
    http_status = 400

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_invalid_code", "reason": self.reason}


class OidcSessionMissing(AdminError):
    http_status = 401

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_session_missing"}


class OidcInvalidSession(AdminError):
    http_status = 401

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_invalid_session"}


class OidcSessionExpired(AdminError):
    http_status = 401

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_session_expired"}


class OidcInvalidToken(AdminError):
    http_status = 401

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_invalid_token", "reason": self.reason}


class OidcRoleForbidden(AdminError):
    http_status = 403

    def __init__(self, *, required: str, has: list[str]) -> None:
        super().__init__(required)
        self.required = required
        self.has = list(has)

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "oidc_role_forbidden",
            "required": self.required,
            "has": self.has,
        }


def register_error_handlers(app: FastAPI) -> None:
    """Enregistre les handlers d'exceptions JSON globaux."""

    async def _admin_handler(_request: Request, exc: AdminError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload())

    app.add_exception_handler(AdminError, _admin_handler)  # type: ignore[arg-type]

    # Remap Pydantic ValidationError(content_too_large) → 413 (au lieu du 422
    # par défaut). Le validator du DTO `PushRequest.content` lève
    # `ValueError("content_too_large")` quand le body UTF-8 dépasse 5 MB ;
    # ce remap aligne la réponse HTTP sur la sémantique RFC 7231 §6.5.11.
    from fastapi.exceptions import RequestValidationError

    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        for err in errors:
            msg = str(err.get("msg") or "")
            if "content_too_large" in msg:
                return JSONResponse(
                    status_code=413,
                    content=ContentTooLarge().to_payload(),
                )
            # Pydantic v2 met l'exception source dans ctx['error'] quand un
            # validator custom raise ValueError — pas JSON-serializable.
            # On stringifie pour préserver l'info sans casser la réponse.
            ctx = err.get("ctx")
            if ctx and "error" in ctx and not isinstance(ctx["error"], str):
                ctx["error"] = str(ctx["error"])
        return JSONResponse(status_code=422, content={"detail": errors})

    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
