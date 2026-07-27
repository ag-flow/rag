import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceSearchTestTab } from "@/pages/workspace/WorkspaceSearchTestTab";
import type { TestQuestion, TestRun } from "@/lib/search-test";

const runMutate = vi.fn();

vi.mock("@/hooks/useSearchTest", () => ({
  useTestQuestions: vi.fn(),
  useTestRuns: vi.fn(),
  useTestRunDetail: vi.fn(() => ({ data: undefined })),
  useSetQuestionEnabled: () => ({ mutate: vi.fn() }),
  useDeleteQuestion: () => ({ mutate: vi.fn() }),
  useRunCampaign: () => ({ mutate: runMutate, isPending: false }),
}));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

import { useTestQuestions, useTestRuns } from "@/hooks/useSearchTest";

const question: TestQuestion = {
  id: "q-1",
  question: "Comment créer un workspace ?",
  expected_path_contains: "6a398cd2",
  family: "paraphrasee",
  enabled: true,
  created_at: "2026-07-27T10:00:00Z",
};

const run: TestRun = {
  id: "run-1",
  started_at: "2026-07-27T11:00:00Z",
  config: { hybrid: false, top_k: 10 },
  metrics: {
    "recall@1": 0.5,
    "recall@5": 0.75,
    "recall@10": 1,
    mrr: 0.62,
    families: { paraphrasee: { "recall@1": 0.5, "recall@5": 0.75, "recall@10": 1, mrr: 0.62 } },
  },
  questions_total: 4,
  questions_failed: 1,
};

function mockData(questions: TestQuestion[], runs: TestRun[]): void {
  vi.mocked(useTestQuestions).mockReturnValue({
    data: questions,
    isLoading: false,
  } as unknown as ReturnType<typeof useTestQuestions>);
  vi.mocked(useTestRuns).mockReturnValue({
    data: runs,
  } as unknown as ReturnType<typeof useTestRuns>);
}

describe("WorkspaceSearchTestTab", () => {
  beforeEach(() => vi.clearAllMocks());

  it("liste les questions et lance une campagne", () => {
    mockData([question], []);
    renderWithProviders(<WorkspaceSearchTestTab workspaceName="ws-1" enabled />);

    expect(screen.getByText("Comment créer un workspace ?")).toBeInTheDocument();
    expect(screen.getByText("paraphrasee")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lancer une campagne" }));
    expect(runMutate).toHaveBeenCalled();
  });

  it("affiche l'historique des campagnes avec métriques et échecs", () => {
    mockData([question], [run]);
    renderWithProviders(<WorkspaceSearchTestTab workspaceName="ws-1" enabled />);

    expect(screen.getByText(/R@1 50 % · R@5 75 % · R@10 100 %/)).toBeInTheDocument();
    expect(screen.getByText("1/4 échecs")).toBeInTheDocument();
    expect(screen.getByText("vectoriel seul")).toBeInTheDocument();
  });

  it("bouton désactivé sans question activée", () => {
    mockData([{ ...question, enabled: false }], []);
    renderWithProviders(<WorkspaceSearchTestTab workspaceName="ws-1" enabled />);
    expect(screen.getByRole("button", { name: "Lancer une campagne" })).toBeDisabled();
  });
});
