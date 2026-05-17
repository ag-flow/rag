import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspacesList } from "@/pages/workspace/WorkspacesList";

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaces: () => ({
    data: [
      {
        id: "1",
        name: "ws-a",
        indexer: { provider: "ollama", model: "mxbai", api_key_ref: null, base_url: null },
        sources_count: 0,
        documents_count: 42,
        last_indexed_at: null,
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "2",
        name: "ws-b",
        indexer: { provider: "openai", model: "text-embedding-3-small", api_key_ref: "key_ref", base_url: null },
        sources_count: 2,
        documents_count: 10,
        last_indexed_at: null,
        created_at: "2026-02-01T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
}));

describe("WorkspacesList", () => {
  it("affiche les workspaces", () => {
    renderWithProviders(
      <WorkspacesList selectedName={null} onSelect={() => {}} onCreate={() => {}} />,
    );
    expect(screen.getByText("ws-a")).toBeInTheDocument();
    expect(screen.getByText("ws-b")).toBeInTheDocument();
  });

  it("déclenche onSelect au click", () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <WorkspacesList selectedName={null} onSelect={onSelect} onCreate={() => {}} />,
    );
    fireEvent.click(screen.getByText("ws-a"));
    expect(onSelect).toHaveBeenCalledWith("ws-a");
  });

  it("met en évidence le workspace sélectionné", () => {
    renderWithProviders(
      <WorkspacesList selectedName="ws-a" onSelect={() => {}} onCreate={() => {}} />,
    );
    const btn = screen.getByText("ws-a").closest("button");
    expect(btn?.className).toContain("bg-blue-50");
  });

  it("déclenche onCreate au click sur le bouton Nouveau", () => {
    const onCreate = vi.fn();
    renderWithProviders(
      <WorkspacesList selectedName={null} onSelect={() => {}} onCreate={onCreate} />,
    );
    fireEvent.click(screen.getByText("+ Nouveau"));
    expect(onCreate).toHaveBeenCalledOnce();
  });
});
