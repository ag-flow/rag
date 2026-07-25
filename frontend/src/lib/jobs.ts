import { api } from "@/lib/api";
import type { GlobalJob, GlobalJobsFilters } from "@/lib/jobs.types";

export const jobsApi = {
  /** Liste globale cross-workspace des jobs d'indexation (tri created_at DESC). */
  listGlobal: (filters: GlobalJobsFilters = {}): Promise<GlobalJob[]> => {
    const params = new URLSearchParams();
    if (filters.limit !== undefined) params.set("limit", String(filters.limit));
    if (filters.workspace) params.set("workspace", filters.workspace);
    if (filters.status) params.set("status", filters.status);
    if (filters.source) params.set("source", filters.source);
    const qs = params.toString();
    return api.get<GlobalJob[]>(`/api/admin/jobs${qs ? `?${qs}` : ""}`);
  },
};
