// Miroir des schemas Pydantic backend (recherche hybride R5).
// `HybridConfig` correspond à la réponse GET/PUT /api/admin/workspaces/{name}/hybrid-config.
// `HybridSpec` correspond au body PUT.
// `PlaygroundSearchResponse` correspond à POST /api/workspaces/{name}/playground/search.

export type LexicalEngine = "fts" | "bm25";

export type HybridConfig = {
  workspace_id: string;
  enabled: boolean;
  rrf_k: number;
  weight_lexical: number;
  weight_vector: number;
  lexical_engine: LexicalEngine;
  rebuild_job_id: string | null;
  created_at: string;
  updated_at: string;
};

export type HybridSpec = {
  enabled: boolean;
  rrf_k: number;
  weight_lexical: number;
  weight_vector: number;
  lexical_engine: LexicalEngine;
};

export type SearchHit = {
  path: string;
  chunk_index: number;
  content: string;
  score: number;
};

export type ChannelHit = {
  path: string;
  chunk_index: number;
  rank: number;
  score: number;
};

export type PlaygroundSearchRequest = {
  query: string;
  top_k?: number;
  min_score?: number;
};

export type PlaygroundSearchResponse = {
  query: string;
  hybrid_enabled: boolean;
  rrf_k: number;
  weight_vector: number;
  weight_lexical: number;
  lexical_engine: LexicalEngine;
  hits: SearchHit[];
  vector_channel: ChannelHit[];
  lexical_channel: ChannelHit[];
};

// Body du 422 renvoyé par le PUT quand bm25 est demandé sans extension pg_search.
export type LexicalEngineUnavailableDetail = {
  error: "lexical_engine_unavailable";
  engine: string;
  hint: string;
};
