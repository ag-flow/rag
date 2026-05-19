import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { ChunkingConfirmReindexAlert } from "@/pages/workspace/ChunkingConfirmReindexAlert";

describe("ChunkingConfirmReindexAlert", () => {
  it("ne rend rien quand open=false", () => {
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={false}
        onOpenChange={() => {}}
        current="paragraph (max=2000, min=200, overlap=200)"
        next="paragraph (max=1500, min=100, overlap=150)"
        onConfirm={() => {}}
        pending={false}
      />,
    );
    expect(screen.queryByText(/Réindexation requise/i)).not.toBeInTheDocument();
  });

  it("affiche current et next quand open=true", () => {
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={() => {}}
        current="paragraph (max=2000, min=200, overlap=200)"
        next="paragraph (max=1500, min=100, overlap=150)"
        onConfirm={() => {}}
        pending={false}
      />,
    );
    expect(screen.getByText(/Réindexation requise/i)).toBeInTheDocument();
    expect(
      screen.getByText("paragraph (max=2000, min=200, overlap=200)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("paragraph (max=1500, min=100, overlap=150)"),
    ).toBeInTheDocument();
  });

  it("appelle onConfirm au clic Réindexer maintenant", () => {
    const onConfirm = vi.fn();
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={() => {}}
        current="a"
        next="b"
        onConfirm={onConfirm}
        pending={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Réindexer maintenant/i }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("appelle onOpenChange(false) au clic Annuler", () => {
    const onOpenChange = vi.fn();
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={onOpenChange}
        current="a"
        next="b"
        onConfirm={() => {}}
        pending={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Annuler$/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("désactive Réindexer maintenant quand pending=true", () => {
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={() => {}}
        current="a"
        next="b"
        onConfirm={() => {}}
        pending={true}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Réindexer maintenant/i }),
    ).toBeDisabled();
  });
});
