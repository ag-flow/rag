import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chunkingStrategiesApi } from "@/lib/chunking-strategies";
import type {
  CompareResult,
  ParserOut,
  PreviewResult,
  RegionRouteSpec,
  StrategyCreate,
  StrategyDetailOut,
  StrategyOut,
  StrategyPatch,
  StrategyPromptOut,
  StrategyPromptSpec,
} from "@/lib/chunking-strategies.types";

const KEY = ["chunking-strategies"];

export function useChunkingStrategies(enabled: boolean = true) {
  return useQuery<StrategyOut[]>({
    queryKey: KEY,
    queryFn: () => chunkingStrategiesApi.list(),
    enabled,
  });
}

export function useChunkingParsers(enabled: boolean = true) {
  return useQuery<ParserOut[]>({
    queryKey: ["chunking-parsers"],
    queryFn: () => chunkingStrategiesApi.listParsers(),
    enabled,
  });
}

export function useStrategyDetail(id: string | null) {
  return useQuery<StrategyDetailOut>({
    queryKey: [...KEY, id],
    queryFn: () => chunkingStrategiesApi.get(id as string),
    enabled: id !== null,
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: KEY });
}

export function useCreateStrategy() {
  const invalidate = useInvalidate();
  return useMutation<StrategyDetailOut, Error, StrategyCreate>({
    mutationFn: (payload) => chunkingStrategiesApi.create(payload),
    onSuccess: invalidate,
  });
}

export function usePatchStrategy() {
  const invalidate = useInvalidate();
  return useMutation<StrategyDetailOut, Error, { id: string; payload: StrategyPatch }>({
    mutationFn: ({ id, payload }) => chunkingStrategiesApi.patch(id, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteStrategy() {
  const invalidate = useInvalidate();
  return useMutation<void, Error, string>({
    mutationFn: (id) => chunkingStrategiesApi.remove(id),
    onSuccess: invalidate,
  });
}

export function useDuplicateStrategy() {
  const invalidate = useInvalidate();
  return useMutation<StrategyDetailOut, Error, { id: string; label: string }>({
    mutationFn: ({ id, label }) => chunkingStrategiesApi.duplicate(id, label),
    onSuccess: invalidate,
  });
}

export function useSetStrategyRoutes() {
  const invalidate = useInvalidate();
  return useMutation<RegionRouteSpec[], Error, { id: string; routes: RegionRouteSpec[] }>({
    mutationFn: ({ id, routes }) => chunkingStrategiesApi.setRoutes(id, routes),
    onSuccess: invalidate,
  });
}

export function useSetStrategyPrompts() {
  const invalidate = useInvalidate();
  return useMutation<StrategyPromptOut[], Error, { id: string; prompts: StrategyPromptSpec[] }>({
    mutationFn: ({ id, prompts }) => chunkingStrategiesApi.setPrompts(id, prompts),
    onSuccess: invalidate,
  });
}

export function usePreviewChunking() {
  return useMutation<
    PreviewResult,
    Error,
    { strategyId: string; content: string; workspaceName?: string; runPrompts?: boolean }
  >({
    mutationFn: ({ strategyId, content, workspaceName, runPrompts }) =>
      chunkingStrategiesApi.preview(strategyId, content, workspaceName, runPrompts),
  });
}

export function useCompareChunking() {
  return useMutation<
    CompareResult,
    Error,
    { strategyA: string; strategyB: string; content: string }
  >({
    mutationFn: ({ strategyA, strategyB, content }) =>
      chunkingStrategiesApi.compare(strategyA, strategyB, content),
  });
}
