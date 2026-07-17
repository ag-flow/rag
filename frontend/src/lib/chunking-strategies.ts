import { api } from "@/lib/api";
import type {
  CompareResult,
  ParserOut,
  PreviewResult,
  RegionRouteSpec,
  StrategyCreate,
  StrategyDetailOut,
  StrategyOut,
  StrategyPatch,
} from "@/lib/chunking-strategies.types";

const BASE = "/api/admin/chunking";

export const chunkingStrategiesApi = {
  listParsers: () => api.get<ParserOut[]>(`${BASE}/parsers`),
  list: () => api.get<StrategyOut[]>(`${BASE}/strategies`),
  get: (id: string) => api.get<StrategyDetailOut>(`${BASE}/strategies/${id}`),
  create: (payload: StrategyCreate) => api.post<StrategyDetailOut>(`${BASE}/strategies`, payload),
  patch: (id: string, payload: StrategyPatch) =>
    api.patch<StrategyDetailOut>(`${BASE}/strategies/${id}`, payload),
  remove: (id: string) => api.delete<void>(`${BASE}/strategies/${id}`),
  duplicate: (id: string, label: string) =>
    api.post<StrategyDetailOut>(`${BASE}/strategies/${id}/duplicate`, { label }),
  setRoutes: (id: string, routes: RegionRouteSpec[]) =>
    api.put<RegionRouteSpec[]>(`${BASE}/strategies/${id}/routes`, { routes }),

  // Dry-run pur : aucun embedding, aucune écriture, aucun job (S5.2).
  preview: (strategyId: string, content: string) =>
    api.post<PreviewResult>(`${BASE}/preview`, { strategy_id: strategyId, content }),
  compare: (strategyA: string, strategyB: string, content: string) =>
    api.post<CompareResult>(`${BASE}/preview/compare`, {
      strategy_a: strategyA,
      strategy_b: strategyB,
      content,
    }),
};
