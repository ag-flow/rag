from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from rag.auth.bearer import require_master_key


def build_app(master_key: str) -> FastAPI:
    app = FastAPI()
    app.state.master_key = master_key

    router = APIRouter()

    @router.get("/admin/ping", dependencies=[Depends(require_master_key)])
    def ping() -> dict[str, str]:
        return {"ok": "yes"}

    app.include_router(router)
    return app


def test_admin_endpoint_requires_authorization() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_admin_endpoint_rejects_bad_token() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_master_key"


def test_admin_endpoint_accepts_master_key() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping", headers={"Authorization": "Bearer mk_test"})
    assert r.status_code == 200
    assert r.json() == {"ok": "yes"}


def test_authorization_scheme_must_be_bearer() -> None:
    app = build_app(master_key="mk_test")
    client = TestClient(app)
    r = client.get("/admin/ping", headers={"Authorization": "Basic mk_test"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_auth_scheme"
