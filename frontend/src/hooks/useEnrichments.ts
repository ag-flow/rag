import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enrichmentsApi } from "@/lib/enrichments";
import type {
  PromptTemplateCreate,
  PromptTemplatePatch,
  TriggerCreate,
  TriggerPatch,
  TriggerPromptCreate,
} from "@/lib/enrichments.types";

const PROMPTS_KEY = ["prompts"] as const;
const triggersKey = (ws: string) => ["triggers", ws] as const;
const triggerPromptsKey = (ws: string, tid: string) =>
  ["trigger-prompts", ws, tid] as const;

export function usePrompts() {
  return useQuery({
    queryKey: PROMPTS_KEY,
    queryFn: enrichmentsApi.listPrompts,
    staleTime: 30_000,
  });
}

export function useCreatePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PromptTemplateCreate) =>
      enrichmentsApi.createPrompt(payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROMPTS_KEY }),
  });
}

export function usePatchPrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: PromptTemplatePatch }) =>
      enrichmentsApi.patchPrompt(id, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROMPTS_KEY }),
  });
}

export function useDeletePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => enrichmentsApi.deletePrompt(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROMPTS_KEY }),
  });
}

export function useTriggers(workspaceName: string) {
  return useQuery({
    queryKey: triggersKey(workspaceName),
    queryFn: () => enrichmentsApi.listTriggers(workspaceName),
    staleTime: 30_000,
  });
}

export function useCreateTrigger(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TriggerCreate) =>
      enrichmentsApi.createTrigger(workspaceName, payload),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: triggersKey(workspaceName) }),
  });
}

export function usePatchTrigger(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ triggerId, payload }: { triggerId: string; payload: TriggerPatch }) =>
      enrichmentsApi.patchTrigger(workspaceName, triggerId, payload),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: triggersKey(workspaceName) }),
  });
}

export function useDeleteTrigger(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (triggerId: string) =>
      enrichmentsApi.deleteTrigger(workspaceName, triggerId),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: triggersKey(workspaceName) }),
  });
}

export function useTriggerPrompts(workspaceName: string, triggerId: string) {
  return useQuery({
    queryKey: triggerPromptsKey(workspaceName, triggerId),
    queryFn: () => enrichmentsApi.listTriggerPrompts(workspaceName, triggerId),
    enabled: !!triggerId,
    staleTime: 30_000,
  });
}

export function useCreateTriggerPrompt(workspaceName: string, triggerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TriggerPromptCreate) =>
      enrichmentsApi.createTriggerPrompt(workspaceName, triggerId, payload),
    onSuccess: () =>
      void qc.invalidateQueries({
        queryKey: triggerPromptsKey(workspaceName, triggerId),
      }),
  });
}

export function useDeleteTriggerPrompt(workspaceName: string, triggerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (promptId: string) =>
      enrichmentsApi.deleteTriggerPrompt(workspaceName, triggerId, promptId),
    onSuccess: () =>
      void qc.invalidateQueries({
        queryKey: triggerPromptsKey(workspaceName, triggerId),
      }),
  });
}

export function useLanguages() {
  return useQuery({
    queryKey: ["languages"],
    queryFn: () => import("@/lib/enrichments").then((m) => m.languagesApi.list()),
    staleTime: 300_000,
  });
}
