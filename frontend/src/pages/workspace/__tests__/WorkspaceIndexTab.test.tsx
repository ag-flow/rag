import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import { WorkspaceIndexTab } from "@/pages/workspace/WorkspaceIndexTab";
import type { PathStrategyEntry } from "@/lib/workspaces.types";

const patchMutate = vi.fn();

vi.mock("@/hooks/useIndexKeys", () => ({
  useIndexKeys: vi.fn(),
  useIndexKeyDetail: vi.fn(() => ({ data: undefined, isLoading: false })),
  usePatchStrategy: () => ({ mutate: patchMutate, isPending: false }),
}));

import { useIndexKeys } from "@/hooks/useIndexKeys";

function makeEntry(overrides: Partial<PathStrategyEntry>): PathStrategyEntry {
  return {
    path: "LESSONS.md",
    strategy: "replace",
    updated_by: "ui",
    chunk_count: 1,
    version_count: 1,
    last_indexed_at: null,
    ...overrides,
  };
}

function mockIndexKeys(
  paths: PathStrategyEntry[],
  isLoading = false,
) {
  vi.mocked(useIndexKeys).mockReturnValue({
    data: { paths, total: paths.length },
    isLoading,
  } as unknown as ReturnType<typeof useIndexKeys>);
}

describe("WorkspaceIndexTab", () => {
  beforeEach(() => {
    patchMutate.mockReset();
  });

  it("affiche 'Aucun fichier indexé' quand la liste est vide", async () => {
    mockIndexKeys([]);
    renderWithProviders(
      <WorkspaceIndexTab workspaceName="my-ws" enabled={true} />,
    );
    await waitFor(() =>
      expect(screen.getByText("Aucun fichier indexé.")).toBeInTheDocument(),
    );
  });

  it("affiche les paths indexés", async () => {
    mockIndexKeys([makeEntry({ path: "LESSONS.md", chunk_count: 3 })]);
    renderWithProviders(
      <WorkspaceIndexTab workspaceName="my-ws" enabled={true} />,
    );
    await waitFor(() =>
      expect(screen.getByText("LESSONS.md")).toBeInTheDocument(),
    );
  });

  it("filtre les paths selon la saisie", async () => {
    const user = userEvent.setup();
    mockIndexKeys([
      makeEntry({ path: "LESSONS.md" }),
      makeEntry({ path: "docs/api.md", chunk_count: 2 }),
    ]);
    renderWithProviders(
      <WorkspaceIndexTab workspaceName="my-ws" enabled={true} />,
    );
    await waitFor(() => expect(screen.getByText("LESSONS.md")).toBeInTheDocument());

    const input = screen.getByPlaceholderText("Filtrer par chemin…");
    await user.type(input, "docs");

    await waitFor(() =>
      expect(screen.queryByText("LESSONS.md")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("docs/api.md")).toBeInTheDocument();
  });

  it("désactive le toggle quand strategy_file", async () => {
    mockIndexKeys([
      makeEntry({ path: "LESSONS.md", strategy: "append", updated_by: "strategy_file" }),
    ]);
    renderWithProviders(
      <WorkspaceIndexTab workspaceName="my-ws" enabled={true} />,
    );
    await waitFor(() =>
      expect(screen.getByText("LESSONS.md")).toBeInTheDocument(),
    );
    // Le Switch rendu quand strategy_file est disabled
    const switches = document.querySelectorAll('[role="switch"]');
    expect(switches.length).toBeGreaterThan(0);
    const disabledSwitch = Array.from(switches).find(
      (el) => el.hasAttribute("disabled") || el.getAttribute("aria-disabled") === "true" || el.getAttribute("data-disabled") === "",
    );
    expect(disabledSwitch).toBeDefined();
  });

  it("appelle patchIndexKeyStrategy au clic du toggle actif", async () => {
    const user = userEvent.setup();
    mockIndexKeys([
      makeEntry({ path: "README.md", strategy: "replace", updated_by: "ui" }),
    ]);
    renderWithProviders(
      <WorkspaceIndexTab workspaceName="my-ws" enabled={true} />,
    );
    await waitFor(() =>
      expect(screen.getByText("README.md")).toBeInTheDocument(),
    );

    const switches = document.querySelectorAll('[role="switch"]');
    expect(switches.length).toBeGreaterThan(0);
    await user.click(switches[0] as HTMLElement);

    await waitFor(() => expect(patchMutate).toHaveBeenCalledTimes(1));
    expect(patchMutate).toHaveBeenCalledWith(
      expect.objectContaining({ path: "README.md", strategy: "append" }),
    );
  });
});
