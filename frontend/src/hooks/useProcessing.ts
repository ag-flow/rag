import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { processingApi } from "@/lib/processing";
import type { ProcessingSettings, ProcessingStatus } from "@/lib/processing";

const PROCESSING_KEY = ["processing"];

export function useProcessing() {
  return useQuery<ProcessingStatus>({
    queryKey: PROCESSING_KEY,
    queryFn: () => processingApi.get(),
    // Occupation instantanée des slots : rafraîchie tant que la page est visible.
    refetchInterval: 10_000,
  });
}

export function useSetProcessing() {
  const qc = useQueryClient();
  return useMutation<ProcessingStatus, Error, ProcessingSettings>({
    mutationFn: (settings) => processingApi.set(settings),
    onSuccess: (status) => qc.setQueryData(PROCESSING_KEY, status),
  });
}
