import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { modelsApi } from "@/lib/models";
import type { ModelCreateRequest, ModelEntry } from "@/lib/models.types";

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
