import { api } from "@/lib/api";
import type { ModelCreateRequest, ModelEntry, PricingData, RerankPairing } from "@/lib/models.types";

const BASE = "/api/admin/models";

export const modelsApi = {
  list: () => api.get<ModelEntry[]>(BASE),
  create: (payload: ModelCreateRequest) => api.post<ModelEntry>(BASE, payload),
  delete: (provider: string, model: string) =>
    api.delete<void>(`${BASE}/${encodeURIComponent(provider)}/${encodeURIComponent(model)}`),
  pricing: () => api.get<PricingData>(`${BASE}/pricing`),
  rerankPairings: () => api.get<RerankPairing[]>(`${BASE}/rerank-pairings`),
};

/** Match LIKE SQL insensible à la casse ('%' = joker), ancré début/fin. */
export function likeMatch(pattern: string, value: string): boolean {
  const escaped = pattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/%/g, ".*");
  return new RegExp(`^${escaped}$`, "i").test(value);
}

/** Le couple (embedder, reranker) est-il préconisé ? Retourne la note de la
 * première règle qui matche, sinon null. */
export function pairingNote(
  pairings: RerankPairing[],
  embed: { provider: string; model: string },
  rerank: { provider: string; model: string },
): string | null {
  for (const p of pairings) {
    if (
      likeMatch(p.embed_provider_like, embed.provider) &&
      likeMatch(p.embed_model_like, embed.model) &&
      likeMatch(p.rerank_provider_like, rerank.provider) &&
      likeMatch(p.rerank_model_like, rerank.model)
    ) {
      return p.note;
    }
  }
  return null;
}
