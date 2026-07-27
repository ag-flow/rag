import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../workspace/__tests__/testUtils";
import { PromptsPage } from "@/pages/PromptsPage";
import type { PromptTemplate } from "@/lib/enrichments.types";

vi.mock("@/lib/enrichments", () => ({
  enrichmentsApi: {
    listPrompts: vi.fn(),
    patchPrompt: vi.fn(),
    deletePrompt: vi.fn(),
    createPrompt: vi.fn(),
    listLanguages: vi.fn().mockResolvedValue([]),
  },
}));

import { enrichmentsApi } from "@/lib/enrichments";

const listPrompts = vi.mocked(enrichmentsApi.listPrompts);
const patchPrompt = vi.mocked(enrichmentsApi.patchPrompt);

const makePrompt = (over: Partial<PromptTemplate>): PromptTemplate => ({
  id: "p1",
  name: "mon-prompt",
  language: "md",
  description: "desc",
  metadata_key: "summary",
  result_type: "text",
  result_schema: null,
  prompt: "Résume ce document.",
  target: "document",
  timing: "post_index_metadata",
  prompt_version: 1,
  is_system: false,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
  ...over,
});

describe("PromptsPage — édition", () => {
  beforeEach(() => {
    listPrompts.mockReset();
    patchPrompt.mockReset();
  });

  it("édite un prompt utilisateur via le dialog (PATCH)", async () => {
    listPrompts.mockResolvedValue([makePrompt({})]);
    patchPrompt.mockResolvedValue(makePrompt({ prompt: "Nouveau corps." }));
    renderWithProviders(<PromptsPage />);
    await screen.findByText("mon-prompt");

    fireEvent.click(screen.getByRole("button", { name: "Modifier" }));
    expect(await screen.findByText("Modifier le prompt")).toBeInTheDocument();

    const body = screen.getByDisplayValue("Résume ce document.");
    fireEvent.change(body, { target: { value: "Nouveau corps." } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => {
      expect(patchPrompt).toHaveBeenCalledWith("p1", {
        description: "desc",
        prompt: "Nouveau corps.",
      });
    });
  });

  it("désactive l'édition et la suppression d'un prompt système", async () => {
    listPrompts.mockResolvedValue([makePrompt({ id: "s1", name: "sys", is_system: true })]);
    renderWithProviders(<PromptsPage />);
    await screen.findByText("sys");

    expect(screen.getByRole("button", { name: "Modifier" })).toBeDisabled();
  });
});
