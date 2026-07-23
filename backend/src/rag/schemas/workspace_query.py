from __future__ import annotations

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """Contenu reconstruit d'un document indexé (équivalent REST de get_document)."""

    path: str
    content: str
    is_legacy: bool
    is_code_structured: bool
    sections_count: int


class FileHit(BaseModel):
    path: str
    chunk_index: int
    content: str
    enrichment_key: str | None = None
    source_path: str | None = None


class FilesResponse(BaseModel):
    """Occurrences littérales d'un motif (équivalent REST de search_files)."""

    pattern: str
    mode: str
    count: int
    hits: list[FileHit]


class EnrichmentResponse(BaseModel):
    """Enrichissement LLM d'un document (équivalent REST de get_enrichment)."""

    path: str
    key: str
    result: str
    result_type: str


class RerankConfigView(BaseModel):
    """Vue fonctionnelle de la config de reranking (sans réf secrète api_key_ref)."""

    provider: str
    model: str
    base_url: str | None = None
    top_k_pre_rerank: int


class HybridConfigView(BaseModel):
    """Vue fonctionnelle de la config de recherche hybride."""

    enabled: bool
    rrf_k: int
    weight_lexical: float
    weight_vector: float
    lexical_engine: str
