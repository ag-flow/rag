import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sourceWebhooksApi } from "@/lib/source-webhooks";

export function useEnableWebhook(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceName: string) =>
      sourceWebhooksApi.enable(workspaceName, sourceName),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sources", workspaceName] });
    },
  });
}

export function useDisableWebhook(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sourceName: string) =>
      sourceWebhooksApi.disable(workspaceName, sourceName),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sources", workspaceName] });
    },
  });
}

export function useRotateWebhookSecret(workspaceName: string) {
  return useMutation({
    mutationFn: (sourceName: string) =>
      sourceWebhooksApi.rotateSecret(workspaceName, sourceName),
  });
}
