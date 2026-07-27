import { api } from "@/lib/api";
import type {
  ModelCreateRequest,
  ModelEntry,
  ModelUpdateRequest,
  PricingData,
  ProviderUrlTemplates,
  RerankPairing,
} from "@/lib/models.types";

const BASE = "/api/admin/models";

export const modelsApi = {
  list: () => api.get<ModelEntry[]>(BASE),
  create: (payload: ModelCreateRequest) => api.post<ModelEntry>(BASE, payload),
  delete: (provider: string, model: string) =>
    api.delete<void>(`${BASE}/${encodeURIComponent(provider)}/${encodeURIComponent(model)}`),
  update: (provider: string, model: string, payload: ModelUpdateRequest) =>
    api.patch<ModelEntry>(
      `${BASE}/${encodeURIComponent(provider)}/${encodeURIComponent(model)}`,
      payload,
    ),
  pricing: () => api.get<PricingData>(`${BASE}/pricing`),
  rerankPairings: () => api.get<RerankPairing[]>(`${BASE}/rerank-pairings`),
  urlTemplates: () => api.get<ProviderUrlTemplates>("/api/admin/providers/url-templates"),
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

/** URL réelle d'appel — miroir client de services/provider_urls.resolve_url. */
export function resolveCallUrl(
  templates: ProviderUrlTemplates,
  capability: "embeddings" | "chat" | "rerank",
  args: { provider: string; model: string; baseUrl?: string | null; template?: string | null },
): string | null {
  const entry = templates[args.provider]?.[capability];
  let tpl = (args.template ?? "").trim() || entry?.template;
  if (!tpl) return null;
  tpl = tpl.replaceAll("{url}", "{base_url}");
  const base = (args.baseUrl ?? "").trim() || entry?.default_base_url || "";
  if (tpl.includes("{base_url}") && !base) return null;
  return tpl.replaceAll("{base_url}", base.replace(/\/+$/, "")).replaceAll("{model}", args.model);
}
