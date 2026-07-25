// Miroir des schemas Pydantic backend (GET /api/admin/jobs).
// `GlobalJob` correspond à GlobalJobResponse : JobResponse + workspace_name.
import type { Job, JobSource } from "@/lib/workspaces.types";

export type GlobalJob = Job & { workspace_name: string };

export type GlobalJobsFilters = {
  workspace?: string;
  status?: Job["status"];
  source?: JobSource;
  limit?: number;
};
