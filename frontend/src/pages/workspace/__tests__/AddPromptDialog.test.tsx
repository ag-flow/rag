import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { AddPromptDialog } from "../AddPromptDialog";

const mutation = () => ({
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  error: null,
  data: undefined,
});

vi.mock("@/hooks/useEnrichments", () => ({
  useCreatePrompt: vi.fn(() => mutation()),
  useLanguages: vi.fn(() => ({ data: [], isLoading: false })),
}));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: vi.fn() }) }));

describe("AddPromptDialog — aide par mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("affiche l'aide du mode document par défaut (non liable dans une stratégie)", () => {
    renderWithProviders(<AddPromptDialog open onOpenChange={vi.fn()} />);

    expect(
      screen.getByText(/n'apparaît PAS dans les stratégies de découpage/),
    ).toBeInTheDocument();
  });

  it("initialMode=chunk présélectionne le mode et affiche son aide (liable)", () => {
    renderWithProviders(<AddPromptDialog open onOpenChange={vi.fn()} initialMode="chunk" />);

    expect(screen.getByText(/Liable dans une stratégie de découpage/)).toBeInTheDocument();
    // Le hint inline (placeholders + cache) n'apparaît que hors mode document.
    expect(screen.getByText(/jamais actif par défaut/)).toBeInTheDocument();
  });
});
