import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workspacesApi } from "@/lib/workspaces";
import type {
  ApiKeyRotateResponse,
  Job,
  Source,
  SourceCreateRequest,
  SourceUpdateRequest,
  Workspace,
  WorkspaceCreate,
  WorkspaceCreateResponse,
  WorkspacePatchRequest,
} from "@/lib/workspaces.types";

// ─── Queries ──────────────────────────────────────────────────────────────

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspacesApi.list(),
  });
}

export function useWorkspace(name: string | null) {
  return useQuery({
    queryKey: ["workspace", name],
    queryFn: () => workspacesApi.get(name as string),
    enabled: name !== null,
  });
}

export function useWorkspaceSources(name: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", name, "sources"],
    queryFn: () => workspacesApi.listSources(name as string),
    enabled: name !== null && enabled,
  });
}

export function useWorkspaceJobs(name: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", name, "jobs"],
    queryFn: () => workspacesApi.listJobs(name as string),
    enabled: name !== null && enabled,
  });
}

export function useWorkspaceJobFiles(name: string, jobId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", name, "jobs", jobId, "files"],
    queryFn: () => workspacesApi.listJobFiles(name, jobId),
    enabled,
  });
}

// ─── Mutations ────────────────────────────────────────────────────────────

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation<WorkspaceCreateResponse, Error, WorkspaceCreate>({
    mutationFn: (payload) => workspacesApi.create(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useUpdateApiKeyRef(name: string) {
  const qc = useQueryClient();
  return useMutation<Workspace, Error, WorkspacePatchRequest>({
    mutationFn: (payload) => workspacesApi.patch(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useDeleteWorkspace() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) => workspacesApi.delete(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useRotateApiKey(name: string) {
  const qc = useQueryClient();
  return useMutation<ApiKeyRotateResponse, Error, void>({
    mutationFn: () => workspacesApi.rotateApiKey(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}

export function useRevealApiKey(name: string) {
  return useMutation<ApiKeyRotateResponse, Error, void>({
    mutationFn: () => workspacesApi.revealApiKey(name),
  });
}

export function useReindex(name: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => workspacesApi.reindex(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}

export function useAddSource(name: string) {
  const qc = useQueryClient();
  return useMutation<Source, Error, SourceCreateRequest>({
    mutationFn: (payload) => workspacesApi.addSource(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "sources"] });
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}

export function useUpdateSource(name: string) {
  const qc = useQueryClient();
  return useMutation<Source, Error, { sourceId: string; payload: SourceUpdateRequest }>({
    mutationFn: ({ sourceId, payload }) => workspacesApi.updateSource(name, sourceId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "sources"] });
    },
  });
}

export function useDeleteSource(name: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (sourceId) => workspacesApi.deleteSource(name, sourceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "sources"] });
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}

export function useTestSourceConnection(name: string) {
  return useMutation<{ success: boolean; message: string | null }, Error, string>({
    mutationFn: (sourceId) => workspacesApi.testSourceConnection(name, sourceId),
  });
}

export function useTriggerSourceSync(name: string) {
  const qc = useQueryClient();
  return useMutation<Job, Error, string>({
    mutationFn: (sourceId) => workspacesApi.triggerSourceSync(name, sourceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
    },
  });
}
