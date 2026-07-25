from __future__ import annotations

import structlog
from fastapi import Request
from pydantic import BaseModel, Field

from rag.indexer.providers.factory import make_provider
from rag.rerank.providers.factory import make_rerank_provider
from rag.secrets.refs import as_vault_ref, is_vault_ref

log = structlog.get_logger(__name__)

_PING_TEXT = "ping ragflow — test de vectorisation"
_RERANK_QUERY = "test de reranking"
_RERANK_DOCS = ["premier document de test", "second document de test"]


class EndpointTestIndexer(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None


class EndpointTestRerank(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None


class EndpointTestRequest(BaseModel):
    indexer: EndpointTestIndexer
    rerank: EndpointTestRerank | None = None


class SectionResult(BaseModel):
    ok: bool
    message: str


class EndpointTestResult(BaseModel):
    vectorization: SectionResult
    rerank: SectionResult | None = None


async def _resolve_key(request: Request, ref: str | None) -> str | None:
    """Résout une réf de clé (vault_ref complet ou clé logique + vault défaut)."""
    if not ref:
        return None
    resolver = request.app.state.resolver
    default_vault = await request.app.state.client_provider.get_default_vault_name()
    if is_vault_ref(ref) or default_vault is not None:
        return await resolver.resolve_with_retry(as_vault_ref(ref, default_vault or ""))
    return None


async def _embedding_service_for(request: Request, provider: str, model: str) -> str | None:
    pool = request.app.state.pools.config_pool
    return await pool.fetchval(
        "SELECT service FROM model_dimensions WHERE provider = $1 AND model = $2",
        provider,
        model,
    )


async def _test_vectorization(request: Request, spec: EndpointTestIndexer) -> SectionResult:
    service = await _embedding_service_for(request, spec.provider, spec.model)
    if service is None:
        return SectionResult(
            ok=False,
            message=(
                f"modèle inconnu du registre : {spec.provider}/{spec.model} "
                "(page Models)"
            ),
        )
    try:
        api_key = await _resolve_key(request, spec.api_key_ref)
        embedder = make_provider(
            service=service,
            provider=spec.provider,
            model=spec.model,
            api_key=api_key,
            base_url=spec.base_url,
        )
        vector = await embedder.embed_query(_PING_TEXT)
    except Exception as exc:  # message contextualisé par l'adapter (url + modèle)
        return SectionResult(ok=False, message=str(exc))
    return SectionResult(ok=True, message=f"OK — vecteur de {len(vector)} dimensions")


async def _test_rerank(request: Request, spec: EndpointTestRerank) -> SectionResult:
    try:
        api_key = await _resolve_key(request, spec.api_key_ref)
        reranker = make_rerank_provider(
            provider=spec.provider,
            model=spec.model,
            api_key=api_key,
            base_url=spec.base_url,
        )
        results = await reranker.rerank(query=_RERANK_QUERY, documents=_RERANK_DOCS, top_k=2)
    except Exception as exc:
        return SectionResult(ok=False, message=str(exc))
    return SectionResult(ok=True, message=f"OK — {len(results)} document(s) reclassé(s)")


async def run_endpoint_test(request: Request, req: EndpointTestRequest) -> EndpointTestResult:
    """Exécute les tests réels (embedding + rerank éventuel) de la config saisie."""
    vec = await _test_vectorization(request, req.indexer)
    rr = await _test_rerank(request, req.rerank) if req.rerank is not None else None
    log.info(
        "endpoint_test.run",
        vectorization_ok=vec.ok,
        rerank_ok=rr.ok if rr else None,
        provider=req.indexer.provider,
        model=req.indexer.model,
    )
    return EndpointTestResult(vectorization=vec, rerank=rr)
