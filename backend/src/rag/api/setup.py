from __future__ import annotations

import bcrypt
import structlog
from fastapi import APIRouter, Request

from rag.api.errors import SetupAlreadyDone
from rag.auth.bearer import _LOCAL_SESSION_KEY
from rag.schemas.local_auth import InitAdminRequest, InitAdminResponse, SetupStatusResponse

log = structlog.get_logger(__name__)


def build_setup_router() -> APIRouter:
    """Endpoints de premier démarrage (pas d'auth requise)."""
    router = APIRouter(prefix="/api/setup", tags=["setup"])

    @router.get("/status", response_model=SetupStatusResponse)
    async def setup_status(request: Request) -> SetupStatusResponse:
        local_auth = request.app.state.local_auth
        count = await local_auth.user_count()
        return SetupStatusResponse(needs_setup=count == 0)

    @router.post("/init-admin", response_model=InitAdminResponse, status_code=201)
    async def init_admin(payload: InitAdminRequest, request: Request) -> InitAdminResponse:
        local_auth = request.app.state.local_auth
        pool = request.app.state.pools.config_pool

        async with pool.acquire() as conn, conn.transaction():
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            if count > 0:
                raise SetupAlreadyDone()
            password_hash = bcrypt.hashpw(
                payload.password.encode("utf-8"), bcrypt.gensalt(12)
            ).decode("utf-8")
            await conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES ($1, $2, $3)",
                payload.username,
                payload.email,
                password_hash,
            )

        request.session[_LOCAL_SESSION_KEY] = local_auth.build_session_payload(payload.username, payload.email)
        log.info("setup.init_admin.done", username=payload.username)
        return InitAdminResponse()

    return router
