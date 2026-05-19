import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chunkingApi, type UpsertChunkingResult } from "@/lib/chunking";
import type { ChunkingConfig, ChunkingSpec } from "@/lib/chunking.types";

/**
 * Récupère la chunking_config du workspace. Config obligatoire : un workspace
 * en a toujours une (créée à l'init via M9-T6 backend).
 */
export function useChunkingConfig(name: string, enabled: boolean) {
  return useQuery<ChunkingConfig>({
    queryKey: ["workspace", name, "chunking"],
    queryFn: () => chunkingApi.get(name),
    enabled,
  });
}

type UpsertVars = { payload: ChunkingSpec; confirm: boolean };

/**
 * Upsert chunking_config. Le caller passe confirm=false au premier essai —
 * une ApiError 409 (chunking_change_requires_reindex) doit être interceptée
 * par le composant pour afficher le dialog de confirmation, qui rappellera
 * la mutation avec confirm=true.
 */
export function useUpsertChunkingConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<UpsertChunkingResult, Error, UpsertVars>({
    mutationFn: ({ payload, confirm }) =>
      chunkingApi.upsert(name, payload, confirm),
    onSuccess: (result) => {
      if (result.status !== "no_change") {
        void qc.invalidateQueries({
          queryKey: ["workspace", name, "chunking"],
        });
      }
      if (result.status === "reindex_triggered") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
      }
    },
  });
}
