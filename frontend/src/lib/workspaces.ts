import { api } from "@/lib/api";
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

const BASE = "/api/admin/workspaces";

export const workspacesApi = {
  list: () => api.get<Workspace[]>(BASE),

  get: (name: string) => api.get<Workspace>(`${BASE}/${name}`),

  create: (payload: WorkspaceCreate) => api.post<WorkspaceCreateResponse>(BASE, payload),

  patch: (name: string, payload: WorkspacePatchRequest) =>
    api.patch<Workspace>(`${BASE}/${name}`, payload),

  delete: (name: string) => api.delete<void>(`${BASE}/${name}`),

  rotateApiKey: (name: string) =>
    api.post<ApiKeyRotateResponse>(`${BASE}/${name}/rotate-apikey`, {}),

  revealApiKey: (name: string) => api.get<ApiKeyRotateResponse>(`${BASE}/${name}/apikey`),

  reindex: (name: string) => api.post<void>(`${BASE}/${name}/reindex?confirm=true`, {}),

  listSources: (name: string) => api.get<Source[]>(`${BASE}/${name}/sources`),

  addSource: (name: string, payload: SourceCreateRequest) =>
    api.post<Source>(`${BASE}/${name}/sources`, payload),

  updateSource: (name: string, sourceId: string, payload: SourceUpdateRequest) =>
    api.patch<Source>(`${BASE}/${name}/sources/${sourceId}`, payload),

  deleteSource: (name: string, sourceId: string) =>
    api.delete<void>(`${BASE}/${name}/sources/${sourceId}`),

  listJobs: (name: string) => api.get<Job[]>(`${BASE}/${name}/jobs`),
};
