import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  chunkingApi,
  type SetDefaultStrategyResult,
  type SetEngineResult,
  type UpsertChunkingResult,
} from "@/lib/chunking";
import type { ChunkingConfig, ChunkingEngine, ChunkingSpec } from "@/lib/chunking.types";

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
    mutationFn: ({ payload, confirm }) => chunkingApi.upsert(name, payload, confirm),
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

type EngineVars = { engine: ChunkingEngine; confirm: boolean };

/**
 * Bascule du moteur de chunking (`legacy` ↔ `structured`). Même contrat 409
 * que `useUpsertChunkingConfig` : le composant intercepte l'ApiError pour
 * afficher le dialog de confirmation, qui rappelle la mutation confirm=true.
 */
export function useSetChunkingEngine(name: string) {
  const qc = useQueryClient();
  return useMutation<SetEngineResult, Error, EngineVars>({
    mutationFn: ({ engine, confirm }) => chunkingApi.setEngine(name, engine, confirm),
    onSuccess: (result) => {
      if (result.status !== "no_change") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "chunking"] });
      }
      if (result.status === "reindex_triggered") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
      }
    },
  });
}

type DefaultStrategyVars = { strategyId: string | null; confirm: boolean };

/**
 * Binding par id de la stratégie par défaut du workspace. Même contrat 409
 * que `useUpsertChunkingConfig` : le composant intercepte pour confirmer la
 * réindexation. Invalide aussi le catalogue (compteur « utilisée par N »).
 */
export function useSetDefaultStrategy(name: string) {
  const qc = useQueryClient();
  return useMutation<SetDefaultStrategyResult, Error, DefaultStrategyVars>({
    mutationFn: ({ strategyId, confirm }) =>
      chunkingApi.setDefaultStrategy(name, strategyId, confirm),
    onSuccess: (result) => {
      if (result.status !== "no_change") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "chunking"] });
        void qc.invalidateQueries({ queryKey: ["chunking-strategies"] });
      }
      if (result.status === "reindex_triggered") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
      }
    },
  });
}
