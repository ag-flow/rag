import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { JobDetailPanel } from "@/pages/workspace/JobDetailPanel";
import type { Job } from "@/lib/workspaces.types";

const { mockFiles } = vi.hoisted(() => ({
  mockFiles: {
    value: {
      data: undefined as
        | { files: { path: string; change_type: string }[]; total: number; limit: number }
        | undefined,
      isLoading: false,
      isError: false,
    },
  },
}));

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaceJobFiles: () => mockFiles.value,
}));

const baseJob: Job = {
  id: "j1",
  triggered_by: "schedule",
  status: "done",
  files_changed: 3,
  files_skipped: 10,
  error_message: null,
  started_at: "2026-05-28T16:33:01Z",
  finished_at: "2026-05-28T16:33:11Z",
  duration_ms: 10100,
};

describe("JobDetailPanel", () => {
  beforeEach(() => {
    mockFiles.value = { data: undefined, isLoading: false, isError: false };
  });

  it("liste les fichiers modifiés", () => {
    mockFiles.value = {
      data: {
        files: [
          { path: "guides/new.md", change_type: "added" },
          { path: "docs/intro.md", change_type: "modified" },
        ],
        total: 2,
        limit: 1000,
      },
      isLoading: false,
      isError: false,
    };
    renderWithProviders(<JobDetailPanel name="wrk1" job={baseJob} />);
    expect(screen.getByText("guides/new.md")).toBeInTheDocument();
    expect(screen.getByText("docs/intro.md")).toBeInTheDocument();
  });

  it("affiche 'aucun détail' quand la liste est vide", () => {
    mockFiles.value = {
      data: { files: [], total: 0, limit: 1000 },
      isLoading: false,
      isError: false,
    };
    renderWithProviders(<JobDetailPanel name="wrk1" job={baseJob} />);
    expect(screen.getByText(/aucun détail de fichier/i)).toBeInTheDocument();
  });

  it("affiche le message d'erreur du job en erreur", () => {
    mockFiles.value = { data: { files: [], total: 0, limit: 1000 }, isLoading: false, isError: false };
    const errored: Job = { ...baseJob, status: "error", error_message: "boom" };
    renderWithProviders(<JobDetailPanel name="wrk1" job={errored} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("affiche le compteur de fichiers supplémentaires si total > limit", () => {
    mockFiles.value = {
      data: { files: [{ path: "a.md", change_type: "added" }], total: 1500, limit: 1000 },
      isLoading: false,
      isError: false,
    };
    renderWithProviders(<JobDetailPanel name="wrk1" job={baseJob} />);
    // "+ 500 fichiers supplémentaires" est affiché (total - limit = 500)
    const matches = screen.getAllByText(/500/);
    expect(matches.length).toBeGreaterThan(0);
    expect(matches.some((el) => /500 fichiers/i.test(el.textContent ?? ""))).toBe(true);
  });
});
