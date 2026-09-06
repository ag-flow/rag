import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { searchTestApi } from "@/lib/search-test";
import type { TestQuestion, TestRun } from "@/lib/search-test";

const questionsKey = (ws: string) => ["search-test", ws, "questions"];
const runsKey = (ws: string) => ["search-test", ws, "runs"];

export function useTestQuestions(ws: string, enabled: boolean) {
  return useQuery<TestQuestion[]>({
    queryKey: questionsKey(ws),
    queryFn: () => searchTestApi.listQuestions(ws),
    enabled,
  });
}

export function useSetQuestionEnabled(ws: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, { id: string; enabled: boolean }>({
    mutationFn: ({ id, enabled }) => searchTestApi.setEnabled(ws, id, enabled),
    onSuccess: () => void qc.invalidateQueries({ queryKey: questionsKey(ws) }),
  });
}

export function useDeleteQuestion(ws: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => searchTestApi.deleteQuestion(ws, id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: questionsKey(ws) }),
  });
}

export function useRunCampaign(ws: string) {
  const qc = useQueryClient();
  return useMutation<TestRun, Error, void>({
    mutationFn: () => searchTestApi.run(ws),
    onSuccess: () => void qc.invalidateQueries({ queryKey: runsKey(ws) }),
  });
}

export function useTestRuns(ws: string, enabled: boolean) {
  return useQuery<TestRun[]>({
    queryKey: runsKey(ws),
    queryFn: () => searchTestApi.listRuns(ws),
    enabled,
  });
}

export function useTestRunDetail(ws: string, runId: string | null) {
  return useQuery<TestRun>({
    queryKey: ["search-test", ws, "run", runId],
    queryFn: () => searchTestApi.getRun(ws, runId as string),
    enabled: runId != null,
  });
}
