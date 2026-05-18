import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, isErrorBodyWithDetail } from "@/lib/api";
import { rerankApi } from "@/lib/rerank";
import type { RerankConfig, RerankSpec } from "@/lib/rerank.types";

/**
 * Récupère la config rerank du workspace.
 * Backend renvoie 404 detail="rerank_not_configured" quand pas configuré
 * (cf. backend/src/rag/api/admin/workspaces_rerank.py) — on intercepte ce
 * cas et retourne null pour permettre au composant d'afficher un form vide.
 * Les autres 404 (workspace_not_found) et erreurs sont propagées.
 */
export function useRerankConfig(name: string, enabled: boolean) {
  return useQuery<RerankConfig | null>({
    queryKey: ["workspace", name, "rerank"],
    queryFn: async () => {
      try {
        return await rerankApi.get(name);
      } catch (err) {
        if (
          err instanceof ApiError &&
          err.status === 404 &&
          isErrorBodyWithDetail(err.body, "rerank_not_configured")
        ) {
          return null;
        }
        throw err;
      }
    },
    enabled,
  });
}

export function useUpsertRerankConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<RerankConfig, Error, RerankSpec>({
    mutationFn: (payload) => rerankApi.upsert(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "rerank"] });
    },
  });
}

export function useDeleteRerankConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => rerankApi.delete(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "rerank"] });
    },
  });
}
