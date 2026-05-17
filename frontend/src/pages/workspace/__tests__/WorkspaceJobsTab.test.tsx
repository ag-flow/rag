import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceJobsTab } from "@/pages/workspace/WorkspaceJobsTab";

const mockJobs = [
  {
    id: "job-1",
    triggered_by: "manual" as const,
    status: "done" as const,
    files_changed: 5,
    files_skipped: 2,
    error_message: null,
    started_at: "2026-01-01T10:00:00Z",
    finished_at: "2026-01-01T10:01:00Z",
    duration_ms: 60000,
  },
  {
    id: "job-2",
    triggered_by: "webhook" as const,
    status: "error" as const,
    files_changed: 0,
    files_skipped: 0,
    error_message: "Connection refused",
    started_at: "2026-01-02T10:00:00Z",
    finished_at: "2026-01-02T10:00:05Z",
    duration_ms: 5000,
  },
];

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaceJobs: () => ({
    data: mockJobs,
    isLoading: false,
  }),
}));

describe("WorkspaceJobsTab", () => {
  it("affiche le titre avec le count des jobs", () => {
    renderWithProviders(<WorkspaceJobsTab name="my-workspace" enabled={true} />);
    expect(screen.getByText(/Jobs \(2\)/)).toBeInTheDocument();
  });

  it("affiche les badges de statut", () => {
    renderWithProviders(<WorkspaceJobsTab name="my-workspace" enabled={true} />);
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
  });

  it("affiche le triggered_by", () => {
    renderWithProviders(<WorkspaceJobsTab name="my-workspace" enabled={true} />);
    expect(screen.getByText("manual")).toBeInTheDocument();
    expect(screen.getByText("webhook")).toBeInTheDocument();
  });

  it("affiche le message d'erreur après expand sur un job en erreur", () => {
    renderWithProviders(<WorkspaceJobsTab name="my-workspace" enabled={true} />);
    const errorBadge = screen.getByText("error");
    const row = errorBadge.closest("button");
    expect(row).not.toBeNull();
    fireEvent.click(row!);
    expect(screen.getByText("Connection refused")).toBeInTheDocument();
  });

  it("affiche les changements de fichiers", () => {
    renderWithProviders(<WorkspaceJobsTab name="my-workspace" enabled={true} />);
    // job-1 : 5 ch / 2 sk
    expect(screen.getByText("5 ch / 2 sk")).toBeInTheDocument();
  });
});
