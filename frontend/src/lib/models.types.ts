// Types miroirs du schema Pydantic ModelEntry
// (cf. backend/src/rag/schemas/admin.py:123)

export type ModelEntry = {
  provider: string;
  model: string;
  dimension: number;
  created_at: string;
};

export type ModelCreateRequest = {
  provider: string;
  model: string;
  dimension: number;
};

// ─── Pricing YAML types ───────────────────────────────────────────────────────

export interface ModelPricingEntry {
  name: string;
  dim: number | null;
  price_per_1m: number | null;
  price_per_1m_batch?: number | null;
  statut?: string | null; // "older_model" | "current" | null
  type?: string; // "embedding" | "reranker"
  description?: { fr?: string; en?: string };
  free_tokens?: number | null;
}

export interface ProviderPricing {
  cost_model?: string;
  pricing_url?: string;
  description?: { fr?: string; en?: string };
  models: ModelPricingEntry[];
  cloud_plans?: Record<string, { prix_mois: number; prix_an?: number }>;
}

export interface PricingData {
  meta?: { releve_date?: string; devise?: string; unite_defaut?: string };
  providers?: Record<string, ProviderPricing>;
  remarques_globales?: Array<{ fr?: string; en?: string }>;
}
