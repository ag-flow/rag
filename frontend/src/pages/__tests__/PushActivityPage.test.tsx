import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../workspace/__tests__/testUtils";
import { PushActivityPage } from "@/pages/PushActivityPage";
import type { GlobalJob } from "@/lib/jobs.types";
import type { Workspace } from "@/lib/workspaces.types";

vi.mock("@/lib/jobs", () => ({
  jobsApi: { listGlobal: vi.fn() },
}));
vi.mock("@/lib/workspaces", () => ({
  workspacesApi: { list: vi.fn() },
}));

import { jobsApi } from "@/lib/jobs";
import { workspacesApi } from "@/lib/workspaces";

const listGlobal = vi.mocked(jobsApi.listGlobal);
const listWorkspaces = vi.mocked(workspacesApi.list);

const makeWorkspace = (name: string): Workspace => ({
  id: `id-${name}`,
  name,
  indexer: { provider: "openai", model: "text-embedding-3-small", api_key_ref: null, base_url: null },
  sources_count: 0,
  documents_count: 0,
  last_indexed_at: null,
  created_at: "2026-07-01T00:00:00Z",
});

const makeJob = (workspace: string, status: GlobalJob["status"]): GlobalJob => ({
  id: `job-${workspace}-${status}`,
  workspace_name: workspace,
  triggered_by: "manual",
  status,
  files_changed: 3,
  files_skipped: 1,
  error_message: null,
  started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  finished_at: null,
  duration_ms: 1200,
});

describe("PushActivityPage", () => {
  beforeEach(() => {
    listGlobal.mockReset();
    listWorkspaces.mockReset();
    listWorkspaces.mockResolvedValue([makeWorkspace("ws-a"), makeWorkspace("ws-b")]);
  });

  it("affiche la liste globale des jobs avec workspace, statut et fichiers", async () => {
    listGlobal.mockResolvedValue([makeJob("ws-a", "done"), makeJob("ws-b", "error")]);
    renderWithProviders(<PushActivityPage />);

    await waitFor(() => {
      expect(screen.getByRole("cell", { name: "ws-a" })).toBeInTheDocument();
    });
    expect(screen.getByRole("cell", { name: "ws-b" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Terminé" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Erreur" })).toBeInTheDocument();
    expect(screen.getAllByText("3 modifiés / 1 ignorés")).toHaveLength(2);
    expect(listGlobal).toHaveBeenCalledWith({});
  });

  it("affiche l'état vide quand il n'y a aucun job", async () => {
    listGlobal.mockResolvedValue([]);
    renderWithProviders(<PushActivityPage />);

    await waitFor(() => {
      expect(screen.getByText("Aucun job d'indexation.")).toBeInTheDocument();
    });
  });

  it("refiltre par statut et par workspace via les selects", async () => {
    listGlobal.mockResolvedValue([makeJob("ws-a", "done"), makeJob("ws-b", "error")]);
    renderWithProviders(<PushActivityPage />);

    await waitFor(() => {
      expect(screen.getByRole("cell", { name: "ws-a" })).toBeInTheDocument();
    });

    listGlobal.mockResolvedValue([makeJob("ws-b", "error")]);
    fireEvent.change(screen.getByLabelText("Filtrer par statut"), {
      target: { value: "error" },
    });

    await waitFor(() => {
      expect(listGlobal).toHaveBeenLastCalledWith({ status: "error" });
    });
    await waitFor(() => {
      expect(screen.queryByRole("cell", { name: "ws-a" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("cell", { name: "ws-b" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filtrer par workspace"), {
      target: { value: "ws-b" },
    });

    await waitFor(() => {
      expect(listGlobal).toHaveBeenLastCalledWith({ workspace: "ws-b", status: "error" });
    });
  });
});
