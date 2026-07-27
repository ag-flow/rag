// Types miroirs des schemas Pydantic vault_endpoints
// (cf. backend/src/rag/schemas/vault_endpoints.py)

export type EndpointIndexerSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  /** Limites de débit du service — null = règle désactivée. */
  rpm_limit?: number | null;
  tpm_limit?: number | null;
  /** Requêtes parallèles max — appliqué au niveau endpoint, cross-workspace. */
  max_concurrency?: number | null;
};

export type EndpointRerankSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  top_k_pre_rerank: number;
  /** Limites de débit du service — null = règle désactivée. */
  rpm_limit?: number | null;
  tpm_limit?: number | null;
  /** Requêtes parallèles max — appliqué au niveau endpoint, cross-workspace. */
  max_concurrency?: number | null;
};

/** LLM d'exécution des prompts (enrichissements, contexte, chat Playground). */
export type EndpointLlmSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  /** Limites de débit du service — null = règle désactivée. */
  rpm_limit?: number | null;
  tpm_limit?: number | null;
  /** Requêtes parallèles max — appliqué au niveau endpoint, cross-workspace. */
  max_concurrency?: number | null;
};

export type VaultEndpoint = {
  id: string;
  vault_id: string;
  label: string;
  slug: string;
  indexer: EndpointIndexerSpec;
  rerank: EndpointRerankSpec | null;
  llm: EndpointLlmSpec | null;
  /** Fallback par service (même coffre, un seul niveau) + paramètres breaker. */
  fallback_endpoint_id: string | null;
  failure_threshold: number;
  cooldown_seconds: number;
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
  fallback_endpoint_id?: string | null;
  clear_fallback?: boolean;
  failure_threshold?: number | null;
  cooldown_seconds?: number | null;
};
