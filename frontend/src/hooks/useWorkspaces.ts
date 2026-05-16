import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ApiKeyRotateResponse,
  Workspace,
  WorkspaceCreate,
  WorkspaceCreateResponse,
} from "@/lib/validators";

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.get<Workspace[]>("/api/admin/workspaces"),
  });
}

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: WorkspaceCreate) =>
      api.post<WorkspaceCreateResponse>("/api/admin/workspaces", payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useDeleteWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.delete<void>(`/api/admin/workspaces/${name}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useRotateApiKey() {
  return useMutation({
    mutationFn: (name: string) =>
      api.post<ApiKeyRotateResponse>(
        `/api/admin/workspaces/${name}/rotate-apikey`,
        {},
      ),
  });
}

export function useReindex() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      api.post<void>(
        `/api/admin/workspaces/${name}/reindex?confirm=true`,
        {},
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}
