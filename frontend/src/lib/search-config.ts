import { api, ApiError } from "@/lib/api";
import type {
  HybridConfig,
  HybridSpec,
  LexicalEngineUnavailableDetail,
  PlaygroundSearchRequest,
  PlaygroundSearchResponse,
} from "@/lib/search-config.types";

/** Valeurs par défaut du PUT d'activation initiale (bouton « Activer l'hybride »). */
export const DEFAULT_HYBRID_SPEC: HybridSpec = {
  enabled: true,
  rrf_k: 60,
  weight_lexical: 0.5,
  weight_vector: 0.5,
  lexical_engine: "fts",
};

const base = (name: string) => `/api/admin/workspaces/${name}/hybrid-config`;

export const searchConfigApi = {
  /**
   * Config hybride du workspace. Le backend renvoie 404 quand aucune config
   * n'existe encore (= recherche vectorielle pure) : ce cas est un état
   * nominal, il est traduit en `null` au lieu d'une erreur.
   */
  get: async (name: string): Promise<HybridConfig | null> => {
    try {
      return await api.get<HybridConfig>(base(name));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  upsert: (name: string, payload: HybridSpec) => api.put<HybridConfig>(base(name), payload),

  search: (name: string, payload: PlaygroundSearchRequest) =>
    api.post<PlaygroundSearchResponse>(`/api/workspaces/${name}/playground/search`, payload),
};

/**
 * Garde de type pour le body 422 du PUT hybrid-config :
 * `{detail: {error: "lexical_engine_unavailable", engine, hint}}`.
 */
export function isLexicalEngineUnavailable(
  body: unknown,
): body is { detail: LexicalEngineUnavailableDetail } {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return false;
  }
  const detail = (body as Record<string, unknown>).detail;
  if (typeof detail !== "object" || detail === null) {
    return false;
  }
  const d = detail as Record<string, unknown>;
  return (
    d.error === "lexical_engine_unavailable" &&
    typeof d.engine === "string" &&
    typeof d.hint === "string"
  );
}
