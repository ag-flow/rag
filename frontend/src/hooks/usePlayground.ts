import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { playgroundApi } from "@/lib/playground";
import type { LlmConfigCreate, LlmConfigPatch, PlaygroundChatRequest } from "@/lib/playground.types";

const ROOT = (name: string) => ["playground", name, "llm-configs"] as const;

export function useLlmConfigs(workspaceName: string) {
  return useQuery({
    queryKey: ROOT(workspaceName),
    queryFn: () => playgroundApi.listConfigs(workspaceName),
    staleTime: 30_000,
  });
}

export function useAddLlmConfig(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LlmConfigCreate) =>
      playgroundApi.createConfig(workspaceName, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ROOT(workspaceName) }),
  });
}

export function usePatchLlmConfig(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ configId, payload }: { configId: string; payload: LlmConfigPatch }) =>
      playgroundApi.patchConfig(workspaceName, configId, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ROOT(workspaceName) }),
  });
}

export function useDeleteLlmConfig(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (configId: string) => playgroundApi.deleteConfig(workspaceName, configId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ROOT(workspaceName) }),
  });
}

export function usePlaygroundChat(workspaceName: string) {
  return useMutation({
    mutationFn: (payload: PlaygroundChatRequest) =>
      playgroundApi.chat(workspaceName, payload),
  });
}
