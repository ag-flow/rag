import { api } from "@/lib/api";
import type {
  ApiKeyRotateResponse,
  DetectBranchesResponse,
  Job,
  JobFilesResponse,
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

  testSourceConnection: (name: string, sourceId: string) =>
    api.post<{ success: boolean; message: string | null }>(
      `${BASE}/${name}/sources/${sourceId}/test-connection`,
      {},
    ),

  triggerSourceSync: (name: string, sourceId: string) =>
    api.post<Job>(`${BASE}/${name}/sources/${sourceId}/sync`, {}),

  listJobs: (name: string) => api.get<Job[]>(`${BASE}/${name}/jobs`),

  listJobFiles: (name: string, jobId: string) =>
    api.get<JobFilesResponse>(`${BASE}/${name}/jobs/${jobId}/files`),

  detectBranches: (payload: {
    url: string;
    auth_ref?: string | null;
    ssh_key_ref?: string | null;
    ssh_username?: string | null;
  }) => api.post<DetectBranchesResponse>("/api/admin/sources/detect-branches", payload),
};
