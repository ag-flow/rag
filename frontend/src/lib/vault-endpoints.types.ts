// Types miroirs des schemas Pydantic vault_endpoints
// (cf. backend/src/rag/schemas/vault_endpoints.py)

export type EndpointIndexerSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
};

export type EndpointRerankSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  top_k_pre_rerank: number;
};

export type VaultEndpoint = {
  id: string;
  vault_id: string;
  label: string;
  slug: string;
  indexer: EndpointIndexerSpec;
  rerank: EndpointRerankSpec | null;
  created_at: string;
  updated_at: string;
};

export type EndpointCreate = {
  label: string;
  indexer: EndpointIndexerSpec;
  rerank?: EndpointRerankSpec | null;
};

export type EndpointUpdate = {
  label?: string;
  indexer?: EndpointIndexerSpec;
  rerank?: EndpointRerankSpec | null;
  clear_rerank?: boolean;
};
