import { api } from "@/lib/api";
import type { ModelCreateRequest, ModelEntry } from "@/lib/models.types";

const BASE = "/api/admin/models";

export const modelsApi = {
  list: () => api.get<ModelEntry[]>(BASE),
  create: (payload: ModelCreateRequest) => api.post<ModelEntry>(BASE, payload),
  delete: (provider: string, model: string) =>
    api.delete<void>(`${BASE}/${encodeURIComponent(provider)}/${encodeURIComponent(model)}`),
};
