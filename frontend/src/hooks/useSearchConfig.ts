import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { searchConfigApi } from "@/lib/search-config";
import type {
  HybridConfig,
  HybridSpec,
  PlaygroundSearchRequest,
  PlaygroundSearchResponse,
} from "@/lib/search-config.types";

const KEY = (name: string) => ["workspace", name, "hybrid-config"] as const;

/**
 * Config hybride du workspace. `null` = pas encore de config
 * (recherche vectorielle pure) — cf. searchConfigApi.get qui absorbe le 404.
 */
export function useHybridConfig(name: string, enabled = true) {
  return useQuery<HybridConfig | null>({
    queryKey: KEY(name),
    queryFn: () => searchConfigApi.get(name),
    enabled,
  });
}

export function useSaveHybridConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<HybridConfig, Error, HybridSpec>({
    mutationFn: (payload) => searchConfigApi.upsert(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY(name) });
    },
  });
}

export function usePlaygroundSearch(name: string) {
  return useMutation<PlaygroundSearchResponse, Error, PlaygroundSearchRequest>({
    mutationFn: (payload) => searchConfigApi.search(name, payload),
  });
}
