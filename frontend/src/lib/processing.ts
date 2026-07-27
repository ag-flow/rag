import { api } from "@/lib/api";

// Traitement global (feature a9719d13) — miroir de rag/schemas/processing.py.
export type ProcessingStatus = {
  max_parallel_jobs: number;
  active_jobs: number;
};

export type ProcessingSettings = {
  max_parallel_jobs: number;
};

export const processingApi = {
  get: () => api.get<ProcessingStatus>("/api/admin/processing"),
  set: (settings: ProcessingSettings) =>
    api.put<ProcessingStatus>("/api/admin/processing", settings),
};
