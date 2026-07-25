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

/** LLM d'exécution des prompts (enrichissements, contexte, chat Playground). */
export type EndpointLlmSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
};

export type VaultEndpoint = {
  id: string;
  vault_id: string;
  label: string;
  slug: string;
  indexer: EndpointIndexerSpec;
  rerank: EndpointRerankSpec | null;
  llm: EndpointLlmSpec | null;
  created_at: string;
  updated_at: string;
};

export type EndpointCreate = {
  label: string;
  indexer: EndpointIndexerSpec;
  rerank?: EndpointRerankSpec | null;
  llm?: EndpointLlmSpec | null;
};

export type EndpointUpdate = {
  label?: string;
  indexer?: EndpointIndexerSpec;
  rerank?: EndpointRerankSpec | null;
  clear_rerank?: boolean;
  llm?: EndpointLlmSpec | null;
  clear_llm?: boolean;
};
