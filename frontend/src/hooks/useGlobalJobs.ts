import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "@/lib/jobs";
import type { GlobalJob, GlobalJobsFilters } from "@/lib/jobs.types";

/**
 * Liste globale cross-workspace des jobs d'indexation.
 *
 * Rafraîchissement auto toutes les 10 s tant que la fenêtre est au premier
 * plan (`refetchIntervalInBackground` reste à false, défaut React Query :
 * l'intervalle est suspendu quand la page n'est pas visible).
 */
export function useGlobalJobs(filters: GlobalJobsFilters = {}) {
  return useQuery<GlobalJob[]>({
    queryKey: ["jobs", "global", filters],
    queryFn: () => jobsApi.listGlobal(filters),
    refetchInterval: 10_000,
  });
}
