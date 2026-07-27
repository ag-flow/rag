import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/pages/workspace/__tests__/testUtils";
import { AlgoInfoPanel } from "@/pages/chunking/AlgoInfoPanel";

describe("AlgoInfoPanel", () => {
  it("explique l'algo code (tree-sitter)", () => {
    renderWithProviders(<AlgoInfoPanel algo="code" />);
    expect(screen.getByText("Code — symboles tree-sitter")).toBeInTheDocument();
    expect(screen.getByText(/fonctions, classes, méthodes/)).toBeInTheDocument();
    expect(screen.getByText(/Idéal pour :/)).toBeInTheDocument();
  });

  it("explique l'algo prose (small-to-big)", () => {
    renderWithProviders(<AlgoInfoPanel algo="prose" />);
    expect(screen.getByText("Prose — hiérarchique small-to-big")).toBeInTheDocument();
    expect(screen.getByText(/breadcrumb/)).toBeInTheDocument();
  });
});
