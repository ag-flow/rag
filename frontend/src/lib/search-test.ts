import { api } from "@/lib/api";

// Banc de test de recherche (feature 1a9b8b67) — miroir de admin_search_test.py.
export type TestQuestion = {
  id: string;
  question: string;
  expected_path_contains: string;
  family: "litterale" | "paraphrasee" | "indirecte" | "libre";
  enabled: boolean;
  created_at: string;
};

export type TestRunMetrics = {
  "recall@1": number;
  "recall@5": number;
  "recall@10": number;
  mrr: number;
  families: Record<
    string,
    { "recall@1": number; "recall@5": number; "recall@10": number; mrr: number }
  >;
};

export type TestRunResult = {
  question: string;
  family: string;
  expected_path_contains: string;
  rank: number | null;
};

export type TestRun = {
  id: string;
  started_at: string;
  config: { hybrid: boolean; top_k: number; [k: string]: unknown };
  metrics: TestRunMetrics;
  questions_total: number;
  questions_failed: number;
  results?: TestRunResult[];
};

const base = (ws: string) => `/api/workspaces/${encodeURIComponent(ws)}/search-test`;

export const searchTestApi = {
  listQuestions: (ws: string) => api.get<TestQuestion[]>(`${base(ws)}/questions`),
  setEnabled: (ws: string, id: string, enabled: boolean) =>
    api.patch<void>(`${base(ws)}/questions/${id}`, { enabled }),
  deleteQuestion: (ws: string, id: string) => api.delete<void>(`${base(ws)}/questions/${id}`),
  run: (ws: string) => api.post<TestRun>(`${base(ws)}/runs`, {}),
  listRuns: (ws: string) => api.get<TestRun[]>(`${base(ws)}/runs`),
  getRun: (ws: string, runId: string) => api.get<TestRun>(`${base(ws)}/runs/${runId}`),
};
