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
  workspacesApi: { list: vi.fn(), getJob: vi.fn(), listJobFiles: vi.fn() },
}));

import { jobsApi } from "@/lib/jobs";
import { workspacesApi } from "@/lib/workspaces";

const listGlobal = vi.mocked(jobsApi.listGlobal);
const listWorkspaces = vi.mocked(workspacesApi.list);
const getJob = vi.mocked(workspacesApi.getJob);
const listJobFiles = vi.mocked(workspacesApi.listJobFiles);

const makeWorkspace = (name: string): Workspace => ({
  id: `id-${name}`,
  name,
  endpoint_id: null,
  label: name,
  description: "",
  indexer: {
    provider: "openai",
    model: "text-embedding-3-small",
    api_key_ref: null,
    base_url: null,
  },
  sources_count: 0,
  documents_count: 0,
  last_indexed_at: null,
  created_at: "2026-07-01T00:00:00Z",
});

const makeJob = (workspace: string, status: GlobalJob["status"]): GlobalJob => ({
  id: `job-${workspace}-${status}`,
  workspace_name: workspace,
  triggered_by: "manual",
  source: "rest_api",
  path: "docs/a.md",
  params: null,
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
    getJob.mockReset();
    listJobFiles.mockReset();
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
    // Durée de traitement (duration_ms: 1200 → 1.2 s).
    expect(screen.getAllByText("1.2 s")).toHaveLength(2);
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

  it("affiche la source + le document et filtre par source", async () => {
    listGlobal.mockResolvedValue([makeJob("ws-a", "done")]);
    renderWithProviders(<PushActivityPage />);
    await waitFor(() => {
      expect(screen.getByRole("cell", { name: "ws-a" })).toBeInTheDocument();
    });

    // "API REST" apparaît en option du filtre ET en badge de la ligne (≥ 2).
    expect(screen.getAllByText("API REST").length).toBeGreaterThanOrEqual(2);
    // Le document est un lien profond vers l'onglet Index du workspace.
    const docLink = screen.getByRole("link", { name: "docs/a.md" });
    expect(docLink).toHaveAttribute("href", "/workspaces?ws=ws-a&tab=index&doc=docs%2Fa.md");

    listGlobal.mockResolvedValue([]);
    fireEvent.change(screen.getByLabelText("Filtrer par source"), {
      target: { value: "git" },
    });
    await waitFor(() => {
      expect(listGlobal).toHaveBeenLastCalledWith({ source: "git" });
    });
  });

  it("affiche un rejet d'ingestion avec son motif, sans drill-down", async () => {
    listGlobal.mockResolvedValue([
      {
        ...makeJob("ws-a", "rejected"),
        error_message: "Workspace inconnu ou non autorisé pour cette clé",
      },
    ]);
    renderWithProviders(<PushActivityPage />);
    await waitFor(() => {
      expect(screen.getByRole("cell", { name: "ws-a" })).toBeInTheDocument();
    });

    // "Rejeté" = option du filtre + badge de la ligne (≥ 2).
    expect(screen.getAllByText("Rejeté").length).toBeGreaterThanOrEqual(2);
    expect(
      screen.getByText("Workspace inconnu ou non autorisé pour cette clé"),
    ).toBeInTheDocument();

    // Un rejet n'a pas de job : le clic ne déclenche aucun re-fetch.
    fireEvent.click(screen.getByRole("cell", { name: "ws-a" }));
    expect(getJob).not.toHaveBeenCalled();
  });

  it("affiche un rejet anonyme (workspace inconnu) sans casser la liste", async () => {
    listGlobal.mockResolvedValue([
      {
        ...makeJob("ws-a", "done"),
        id: "rej-1",
        workspace_name: null,
        status: "rejected",
        path: null,
        error_message: "En-tête Authorization manquant",
      },
    ]);
    renderWithProviders(<PushActivityPage />);

    expect(await screen.findByText("En-tête Authorization manquant")).toBeInTheDocument();
    // workspace inconnu affiché en tiret, ligne rendue sans crash.
    expect(screen.getAllByRole("cell", { name: "—" }).length).toBeGreaterThanOrEqual(1);
  });

  it("ouvre le détail d'un job au clic : re-fetch du statut + fichiers", async () => {
    listGlobal.mockResolvedValue([makeJob("ws-a", "pending")]);
    // Statut re-fetché : le job listé était 'pending', il est en fait 'done'.
    getJob.mockResolvedValue({ ...makeJob("ws-a", "done"), triggered_by: "push" });
    listJobFiles.mockResolvedValue({
      files: [{ path: "docs/a.md", change_type: "added" }],
      total: 1,
      limit: 1000,
    });
    renderWithProviders(<PushActivityPage />);

    await waitFor(() => {
      expect(screen.getByRole("cell", { name: "ws-a" })).toBeInTheDocument();
    });

    // Avant ouverture : statut listé 'pending'.
    expect(screen.getByRole("cell", { name: "En attente" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("cell", { name: "ws-a" }));

    // Re-fetch du statut unitaire → le badge passe à 'Terminé'.
    await waitFor(() => {
      expect(getJob).toHaveBeenCalledWith("ws-a", "job-ws-a-pending");
    });
    expect(await screen.findByText("Terminé")).toBeInTheDocument();
    // Le panneau détail liste les fichiers du job.
    await waitFor(() => expect(listJobFiles).toHaveBeenCalled());
    expect(
      await screen.findByText(
        (_c, el) => el?.tagName === "LI" && (el.textContent ?? "").includes("docs/a.md"),
      ),
    ).toBeInTheDocument();
  });
});
