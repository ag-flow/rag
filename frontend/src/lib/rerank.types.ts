// Miroir des schemas Pydantic backend (cf. backend/src/rag/schemas/admin.py).
// `RerankConfig` correspond à RerankConfigResponse.
// `RerankSpec` correspond à RerankSpec (body PUT).

export type RerankProvider = "cohere" | "openai" | "voyage" | "ollama";

export type RerankConfig = {
  workspace_id: string;
  provider: RerankProvider;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  top_k_pre_rerank: number;
  created_at: string;
  updated_at: string;
};

export type RerankSpec = {
  provider: RerankProvider;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  top_k_pre_rerank: number;
};
