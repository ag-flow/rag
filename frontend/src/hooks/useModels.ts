import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { modelsApi } from "@/lib/models";
import type {
  ModelCreateRequest,
  ModelEntry,
  ModelUpdateRequest,
  PricingData,
} from "@/lib/models.types";

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: () => modelsApi.list(),
  });
}

export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation<ModelEntry, Error, ModelCreateRequest>({
    mutationFn: (payload) => modelsApi.create(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation<void, Error, { provider: string; model: string }>({
    mutationFn: ({ provider, model }) => modelsApi.delete(provider, model),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useUpdateModel() {
  const qc = useQueryClient();
  return useMutation<
    ModelEntry,
    Error,
    { provider: string; model: string; payload: ModelUpdateRequest }
  >({
    mutationFn: ({ provider, model, payload }) => modelsApi.update(provider, model, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function usePricing() {
  return useQuery<PricingData>({
    queryKey: ["models-pricing"],
    queryFn: () => modelsApi.pricing(),
    staleTime: 5 * 60 * 1000, // 5 min — le fichier ne change pas souvent
  });
}

export function useRerankPairings() {
  return useQuery({
    queryKey: ["models-rerank-pairings"],
    queryFn: () => modelsApi.rerankPairings(),
    staleTime: 5 * 60 * 1000, // référentiel seedé par migration, quasi statique
  });
}

export function useProviderUrlTemplates() {
  return useQuery({
    queryKey: ["provider-url-templates"],
    queryFn: () => modelsApi.urlTemplates(),
    staleTime: 5 * 60 * 1000, // référentiel statique côté backend
  });
}
