// Miroir des DTOs backend `rag/schemas/chunking_strategies.py` et
// `rag/schemas/chunking_preview.py` (spec chunking §4 et §6).

export const CHUNKING_ALGOS = ["prose", "markdown", "table", "code", "data"] as const;
export type ChunkingAlgo = (typeof CHUNKING_ALGOS)[number];

export const REGION_TYPES = ["prose", "code_fence", "table", "frontmatter", "html_block"] as const;
export type RegionType = (typeof REGION_TYPES)[number];

export const OVERFLOW_POLICIES = ["keep_whole", "split_fallback", "parent_only"] as const;
export type OverflowPolicy = (typeof OVERFLOW_POLICIES)[number];

export interface ParserOut {
  slug: string;
  label: string;
}

export interface RegionRouteSpec {
  region_type: RegionType;
  qualifier: string;
  target_strategy_id: string | null;
  atomic: boolean;
  overflow_policy: OverflowPolicy;
}

export interface StrategyOut {
  id: string;
  label: string;
  slug: string;
  algo: ChunkingAlgo;
  params: Record<string, unknown>;
  parser_slug: string | null;
  is_system: boolean;
  used_by_routes: number;
  used_by_categories: number;
  used_by_triggers: number;
  used_by_workspaces: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyPromptSpec {
  template_id: string;
  order_index: number;
  enabled: boolean;
}

export interface StrategyPromptOut {
  template_id: string;
  template_name: string;
  metadata_key: string;
  target: string;
  order_index: number;
  enabled: boolean;
}

export interface StrategyDetailOut extends StrategyOut {
  routes: RegionRouteSpec[];
  prompts: StrategyPromptOut[];
}

export interface StrategyCreate {
  label: string;
  algo: ChunkingAlgo;
  params: Record<string, unknown>;
  parser_slug?: string | null;
}

export interface StrategyPatch {
  label?: string;
  params?: Record<string, unknown>;
  parser_slug?: string | null;
}

// ─── Preview (dry-run, S5.2) ─────────────────────────────────────────────────

export interface PreviewChunk {
  index: number;
  embed_text: string;
  tokens: number;
  chunk_hash: string;
  parent_key: string;
  region_type: string | null;
  region_qualifier: string | null;
  inline_context: string | null;
}

export interface PreviewRegion {
  region_type: string;
  qualifier: string | null;
  start_line: number;
  end_line: number;
  routed: boolean;
  atomic: boolean;
  overflow_policy: string | null;
  target_strategy_id: string | null;
}

export interface PreviewResult {
  strategy: {
    id: string;
    label: string;
    slug: string;
    algo: ChunkingAlgo;
    parser_slug: string | null;
  };
  parents: { section_key: string; chars: number }[];
  chunks: PreviewChunk[];
  regions: PreviewRegion[];
  prompts: {
    template_id: string;
    template_name: string;
    metadata_key: string;
    target: string;
    enabled: boolean;
  }[];
  prompts_executed: boolean;
  total_chunks: number;
  total_tokens: number;
}

export interface CompareResult {
  a: PreviewResult;
  b: PreviewResult;
  diff: {
    common: number;
    only_a: string[];
    only_b: string[];
  };
}
