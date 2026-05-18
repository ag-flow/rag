import { api } from "@/lib/api";
import type { RerankConfig, RerankSpec } from "@/lib/rerank.types";

const base = (name: string) => `/api/admin/workspaces/${name}/rerank`;

export const rerankApi = {
  get: (name: string) => api.get<RerankConfig>(base(name)),
  upsert: (name: string, payload: RerankSpec) =>
    api.put<RerankConfig>(base(name), payload),
  delete: (name: string) => api.delete<void>(base(name)),
};
