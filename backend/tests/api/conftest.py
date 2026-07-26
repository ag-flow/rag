from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from rag.main import build_app
from rag.secrets.resolver import VaultLookupFailed

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _ApiStubResolver:
    """Resolveur stub : accepte tout `${vault://rag:<known>}` ou `${vault://test:<known>}`,
    refuse le reste.

    Supporte deux catégories de refs :
    - refs logiques connues (openai_embedding_key, voyage_api_key, etc.) → value-of-<logical>
    - refs workspace (wsapi_<name>) → résolu depuis `_secret_store` si présent

    `_secret_store` est partagé avec le stub HarpocrateVaultsService pour que
    `write_secret` persiste la valeur et que le resolver puisse la restituer
    (comportement cohérent pour les tests GET /apikey et MCP auth).
    """

    def __init__(self, secret_store: dict[str, str]) -> None:
        self._secret_store = secret_store
        self.known: set[str] = {
            "openai_embedding_key",
            "voyage_api_key",
            "github_token",
            "vk",
            "k",
        }

    async def resolve(self, ref: str) -> str:
        return await self.resolve_with_retry(ref)

    async def resolve_with_retry(self, ref: str) -> str:
        import re

        m = re.fullmatch(r"\$\{vault://[^:]+:([^}]+)\}", ref)
        if m is None:
            raise AssertionError(f"unexpected ref {ref}")
        logical = m.group(1)
        if logical in self.known:
            return f"value-of-{logical}"
        # Refs workspace (wsapi_<name>) : lookup dans le store partagé.
        if logical in self._secret_store:
            return self._secret_store[logical]
        raise VaultLookupFailed(f"no secret {logical}")


class _ApiStubClientProvider:
    """Stub `HarpocrateClientProvider` : default vault toujours 'rag'.

    Surchargé via le `resolver_factory` du conftest pour que les routers M5c
    (qui appellent `app.state.client_provider.get_default_vault_name()`)
    reçoivent un nom de coffre sans s'appuyer sur la DB.
    """

    async def get_default_vault_name(self) -> str | None:
        return "rag"

    def invalidate(self) -> None:
        pass


def _make_stub_harpocrate_vaults_service(
    secret_store: dict[str, str],
) -> MagicMock:
    """Stub HarpocrateVaultsService pour les tests API.

    get_by_name retourne un VaultSummary mock (vault "rag" existe toujours).
    write_secret persiste la valeur dans `secret_store` (partagé avec le resolver).
    delete_secret efface la valeur du store.
    bind_client_provider est un no-op.
    """
    from rag.schemas.harpocrate_vaults import VaultSummary

    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    vault.base_url = "http://harpocrate-stub:8200"
    vault.name = "rag"
    service.get_by_name = AsyncMock(return_value=vault)
    # create_workspace vérifie l'existence d'un coffre par défaut AVANT tout
    # DDL (chantier endpoints, cac2b8e) — le stub doit répondre en async.
    service.get_default = AsyncMock(return_value=vault)

    async def _write_secret(_conn, *, vault_name: str, path: str, value: str) -> None:
        secret_store[path] = value

    async def _delete_secret(_conn, *, vault_name: str, path: str) -> None:
        secret_store.pop(path, None)

    service.write_secret = _write_secret
    service.delete_secret = _delete_secret
    service.bind_client_provider = MagicMock(return_value=None)
    return service




async def seed_endpoint(
    dsn: str,
    *,
    slug: str,
    provider: str,
    model: str,
    api_key_ref: str | None = "openai_embedding_key",
    base_url: str | None = None,
    rerank: dict | None = None,
    llm: dict | None = None,
    indexer_limits: tuple[int | None, int | None] = (None, None),
) -> str:
    """Seed un endpoint arbitraire (coffre 'rag' créé au besoin) → endpoint_id.

    `rerank` : dict {provider, model, api_key_ref?, base_url?, top_k?, rpm?, tpm?}.
    `llm`    : dict {provider, model, api_key_ref?, base_url?, rpm?, tpm?}.
    `indexer_limits` : (rpm_limit, tpm_limit) du service de vectorisation.
    Sert aux tests qui exercent une sémantique précise (provider inconnu,
    ollama+base_url, rerank à la création…).
    """
    conn = await asyncpg.connect(dsn)
    try:
        vault_id = await conn.fetchval(
            """
            INSERT INTO harpocrate_vaults
                (id, name, label, base_url, api_key_id, api_key_encrypted, is_default)
            VALUES (gen_random_uuid(), 'rag', 'rag', 'http://harpocrate.test', 'k-test',
                    pgp_sym_encrypt('tok-test', 'passphrase-of-at-least-32-characters-long'),
                    true)
            ON CONFLICT (name) DO UPDATE SET label = EXCLUDED.label
            RETURNING id
            """
        )
        rr = rerank or {}
        lm = llm or {}
        endpoint_id = await conn.fetchval(
            """
            INSERT INTO vault_endpoints
                (vault_id, label, slug, indexer_provider, indexer_model,
                 indexer_api_key_ref, indexer_base_url,
                 rerank_provider, rerank_model, rerank_api_key_ref,
                 rerank_base_url, rerank_top_k,
                 llm_provider, llm_model, llm_api_key_ref, llm_base_url,
                 indexer_rpm_limit, indexer_tpm_limit,
                 rerank_rpm_limit, rerank_tpm_limit,
                 llm_rpm_limit, llm_tpm_limit)
            VALUES ($1, $2, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20, $21)
            ON CONFLICT (vault_id, slug) DO UPDATE SET
                indexer_provider = EXCLUDED.indexer_provider,
                indexer_model = EXCLUDED.indexer_model,
                indexer_api_key_ref = EXCLUDED.indexer_api_key_ref,
                indexer_base_url = EXCLUDED.indexer_base_url,
                rerank_provider = EXCLUDED.rerank_provider,
                rerank_model = EXCLUDED.rerank_model,
                rerank_api_key_ref = EXCLUDED.rerank_api_key_ref,
                rerank_base_url = EXCLUDED.rerank_base_url,
                rerank_top_k = EXCLUDED.rerank_top_k,
                llm_provider = EXCLUDED.llm_provider,
                llm_model = EXCLUDED.llm_model,
                llm_api_key_ref = EXCLUDED.llm_api_key_ref,
                llm_base_url = EXCLUDED.llm_base_url,
                indexer_rpm_limit = EXCLUDED.indexer_rpm_limit,
                indexer_tpm_limit = EXCLUDED.indexer_tpm_limit,
                rerank_rpm_limit = EXCLUDED.rerank_rpm_limit,
                rerank_tpm_limit = EXCLUDED.rerank_tpm_limit,
                llm_rpm_limit = EXCLUDED.llm_rpm_limit,
                llm_tpm_limit = EXCLUDED.llm_tpm_limit
            RETURNING id
            """,
            vault_id, slug, provider, model, api_key_ref, base_url,
            rr.get("provider"), rr.get("model"), rr.get("api_key_ref"),
            rr.get("base_url"), rr.get("top_k"),
            lm.get("provider"), lm.get("model"), lm.get("api_key_ref"),
            lm.get("base_url"),
            indexer_limits[0], indexer_limits[1],
            rr.get("rpm"), rr.get("tpm"),
            lm.get("rpm"), lm.get("tpm"),
        )
        return str(endpoint_id)
    finally:
        await conn.close()


def seed_endpoint_sync(dsn: str, **kwargs) -> str:
    """Wrapper synchrone de seed_endpoint pour les tests API (TestClient sync)."""
    import asyncio

    return asyncio.run(seed_endpoint(dsn, **kwargs))


async def _seed_default_endpoint(dsn: str) -> str:
    """Seed un coffre + un endpoint de vectorisation, retourne l'endpoint_id.

    La création de workspace exige désormais un endpoint (préréglage du
    coffre) : chaque TestClient expose `default_endpoint_id` pour les helpers.
    """
    return await seed_endpoint(
        dsn, slug="test-openai", provider="openai", model="text-embedding-3-small"
    )


@pytest_asyncio.fixture
async def admin_client(
    pg_container: str,
) -> AsyncIterator[TestClient]:
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    # Force-set (pas setdefault) : évite la pollution d'env entre modules de test.
    os.environ["RAG_MASTER_KEY"] = "mk_test_e2e_padding_padding_padding_padding"
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )
    # RAG_API_KEY_DEK retiré — les api_keys workspace sont désormais stockées
    # dans Harpocrate (migration 015). On s'assure qu'il n'est PAS dans l'env
    # pour les tests (déjà absent par défaut, mais explicite ici).
    os.environ.pop("RAG_API_KEY_DEK", None)
    os.environ.setdefault("ENVIRONMENT", "dev")

    # Store partagé entre le stub Harpocrate et le resolver :
    # write_secret persiste ici, resolve_with_retry lit ici.
    secret_store: dict[str, str] = {}
    stub_harpo = _make_stub_harpocrate_vaults_service(secret_store)
    admin_resolver = _ApiStubResolver(secret_store)

    def _factory(_cfg, app_in):  # type: ignore[no-untyped-def]
        # Le lifespan a déjà branché un `client_provider` "réel" sur
        # `app.state` ; on le remplace par un stub qui retourne toujours
        # le coffre "rag" pour que les routers M5c puissent fonctionner
        # sans table `harpocrate_vaults` peuplée.
        app_in.state.client_provider = _ApiStubClientProvider()
        # Remplace le HarpocrateVaultsService par le stub pour que
        # create_workspace / rotate_apikey / delete ne s'appuient pas sur
        # la table harpocrate_vaults ni sur une instance Harpocrate réelle.
        app_in.state.harpocrate_vaults_service = stub_harpo
        return admin_resolver

    app = build_app(
        version="0.2.0",
        git_sha="testsha",
        resolver_factory=_factory,  # type: ignore[arg-type]
        migrations_dir=_MIGRATIONS_DIR,
    )
    with TestClient(app) as client:
        # Migrations appliquées par le lifespan → on peut seeder l'endpoint.
        client.default_endpoint_id = await _seed_default_endpoint(pg_container)  # type: ignore[attr-defined]
        yield client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mk_test_e2e_padding_padding_padding_padding"}


@pytest.fixture
def cleanup_ws_dbs_api(pg_container: str) -> Iterator[None]:
    """Droppe les bases workspace créées par LE test (celles de sa config DB).

    Précis et sûr sur un Postgres partagé : on lit `workspaces.rag_base` dans
    la config DB jetable du test — jamais de pattern global qui raterait des
    noms (fuite → collision au run suivant) ou toucherait d'autres bases.
    """
    yield
    import asyncio

    async def _cleanup() -> None:
        config = await asyncpg.connect(pg_container)
        try:
            bases = [r["rag_base"] for r in await config.fetch("SELECT rag_base FROM workspaces")]
        finally:
            await config.close()
        if not bases:
            return
        admin = await asyncpg.connect(pg_container.rsplit("/", 1)[0] + "/postgres")
        try:
            for base in bases:
                await admin.execute(f'DROP DATABASE IF EXISTS "{base}" WITH (FORCE)')
        finally:
            await admin.close()

    # Python 3.12 : get_event_loop() hors boucle courante renvoie une boucle
    # fermée par pytest-asyncio → RuntimeError en teardown. Boucle dédiée.
    asyncio.run(_cleanup())
