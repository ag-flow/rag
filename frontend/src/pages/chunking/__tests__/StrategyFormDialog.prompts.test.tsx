import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/pages/workspace/__tests__/testUtils";
import { StrategyFormDialog } from "@/pages/chunking/StrategyFormDialog";

const mutation = () => ({
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  error: null,
  data: undefined,
});

vi.mock("@/hooks/useChunkingStrategies", () => ({
  useChunkingParsers: vi.fn(() => ({ data: [], isLoading: false })),
  useStrategyDetail: vi.fn(() => ({ data: undefined, isLoading: false })),
  useCreateStrategy: vi.fn(() => mutation()),
  usePatchStrategy: vi.fn(() => mutation()),
  useSetStrategyPrompts: vi.fn(() => mutation()),
}));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock("@/hooks/useEnrichments", () => ({
  usePrompts: vi.fn(() => ({ data: [], isLoading: false })),
  useCreatePrompt: vi.fn(() => mutation()),
  useLanguages: vi.fn(() => ({ data: [], isLoading: false })),
}));

describe("StrategyFormDialog — création de prompt depuis le bloc Prompts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("bibliothèque vide : message explicatif + bouton de création", () => {
    renderWithProviders(<StrategyFormDialog open onOpenChange={vi.fn()} strategy={null} />);

    expect(screen.getByText(/Aucun template liable dans votre bibliothèque/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Créer un prompt (chunk/région)" }),
    ).toBeInTheDocument();
  });

  it("le bouton ouvre le dialog de prompt pré-réglé sur le mode chunk", () => {
    renderWithProviders(<StrategyFormDialog open onOpenChange={vi.fn()} strategy={null} />);

    fireEvent.click(screen.getByRole("button", { name: "Créer un prompt (chunk/région)" }));

    expect(screen.getByText("Nouveau prompt template")).toBeInTheDocument();
    // Pré-réglé sur chunk : l'aide « liable dans une stratégie » est affichée.
    expect(screen.getByText(/Liable dans une stratégie de découpage/)).toBeInTheDocument();
  });
});
