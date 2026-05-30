export type LlmProvider = "claude" | "openai" | "azure-openai" | "ollama";

export type LlmConfig = {
  id: string;
  provider: LlmProvider;
  model: string;
  base_url: string | null;
  api_key_ref: string | null;
  enabled: boolean;
  created_at: string;
};

export type LlmConfigCreate = {
  provider: LlmProvider;
  model: string;
  base_url?: string | null;
  api_key_ref?: string | null;
  enabled?: boolean;
};

export type LlmConfigPatch = {
  enabled: boolean;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ChunkResult = {
  path: string;
  chunk_index: number;
  content: string;
  score: number;
};

export type PlaygroundChatRequest = {
  message: string;
  history: ChatMessage[];
  llm: { provider: string; model: string };
  top_k?: number;
  min_score?: number;
};

export type PlaygroundChatResponse = {
  message: string;
  answer: string;
  chunks: ChunkResult[];
  usage: { prompt_tokens: number; completion_tokens: number };
};
