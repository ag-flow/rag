# backend/tests/api/test_workspace_push_dedup.py
from __future__ import annotations

from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201
    return r.json()["api_key"]


def test_second_push_same_content_returns_skipped(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    """Le fake indexer doit écrire le hash dans `indexed_documents` pour
    que la pré-déduplication du service push voie un hash existant et
    retourne `skipped` au 2e push."""
    api_key = _make_ws(admin_client, admin_headers, "ws_dedup1")

    import asyncpg

    pool_dsn = pg_container

    class _DedupFake:
        def __init__(self) -> None:
            self.index_calls = 0

        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            self.index_calls += 1
            conn = await asyncpg.connect(pool_dsn)
            try:
                await conn.execute(
                    """
                    INSERT INTO indexed_documents
                        (workspace_id, path, content_hash, indexer_used, indexed_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (workspace_id, path) DO UPDATE
                    SET content_hash=EXCLUDED.content_hash,
                        indexer_used=EXCLUDED.indexer_used,
                        indexed_at=EXCLUDED.indexed_at
                    """,
                    kw["workspace_id"],
                    kw["path"],
                    kw["content_hash"],
                    kw["indexer_used"],
                )
            finally:
                await conn.close()
            return 1

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            pass

    fake = _DedupFake()
    admin_client.app.state.indexer = fake  # type: ignore[attr-defined]

    headers = {"Authorization": f"Bearer {api_key}"}

    # 1er push
    r1 = admin_client.post(
        "/workspaces/ws_dedup1/index",
        headers=headers,
        json={"path": "doc.md", "content": "stable content"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "indexed"

    # 2e push même contenu
    r2 = admin_client.post(
        "/workspaces/ws_dedup1/index",
        headers=headers,
        json={"path": "doc.md", "content": "stable content"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "skipped"
    assert body["reason"] == "content_unchanged"
    assert fake.index_calls == 1  # pas de 2e appel à index_file


def test_push_different_content_same_path_reindexes(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_dedup2")

    import asyncpg

    pool_dsn = pg_container

    class _DedupFake:
        def __init__(self) -> None:
            self.calls = 0

        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            self.calls += 1
            conn = await asyncpg.connect(pool_dsn)
            try:
                await conn.execute(
                    """
                    INSERT INTO indexed_documents
                        (workspace_id, path, content_hash, indexer_used, indexed_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (workspace_id, path) DO UPDATE
                    SET content_hash=EXCLUDED.content_hash, indexed_at=now()
                    """,
                    kw["workspace_id"],
                    kw["path"],
                    kw["content_hash"],
                    kw["indexer_used"],
                )
            finally:
                await conn.close()
            return 1

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            pass

    fake = _DedupFake()
    admin_client.app.state.indexer = fake  # type: ignore[attr-defined]

    headers = {"Authorization": f"Bearer {api_key}"}

    r1 = admin_client.post(
        "/workspaces/ws_dedup2/index",
        headers=headers,
        json={"path": "doc.md", "content": "v1"},
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "indexed"

    r2 = admin_client.post(
        "/workspaces/ws_dedup2/index",
        headers=headers,
        json={"path": "doc.md", "content": "v2 different"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "indexed"
    assert body["hash"] != r1.json()["hash"]
    assert fake.calls == 2
