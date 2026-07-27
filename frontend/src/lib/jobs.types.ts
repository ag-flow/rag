// Miroir des schemas Pydantic backend (GET /api/admin/jobs).
// `GlobalJob` correspond à GlobalJobResponse : JobResponse + workspace_name.
import type { Job, JobSource } from "@/lib/workspaces.types";

// workspace_name null = rejet d'ingestion dont le workspace n'a pas pu être lu.
export type GlobalJob = Job & { workspace_name: string | null };

export type GlobalJobsFilters = {
  workspace?: string;
  status?: Job["status"];
  source?: JobSource;
  limit?: number;
};
