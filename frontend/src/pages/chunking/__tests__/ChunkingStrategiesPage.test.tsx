import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/pages/workspace/__tests__/testUtils";
import { ChunkingStrategiesPage } from "@/pages/ChunkingStrategiesPage";
import { useChunkingStrategies } from "@/hooks/useChunkingStrategies";
import type { StrategyOut } from "@/lib/chunking-strategies.types";

const mutation = () => ({
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  error: null,
  data: undefined,
});

vi.mock("@/hooks/useChunkingStrategies", () => ({
  useChunkingStrategies: vi.fn(),
  useChunkingParsers: vi.fn(() => ({ data: [], isLoading: false })),
  useStrategyDetail: vi.fn(() => ({ data: undefined, isLoading: false })),
  useCreateStrategy: vi.fn(() => mutation()),
  usePatchStrategy: vi.fn(() => mutation()),
  useDeleteStrategy: vi.fn(() => mutation()),
  useDuplicateStrategy: vi.fn(() => mutation()),
  useSetStrategyRoutes: vi.fn(() => mutation()),
  useSetStrategyPrompts: vi.fn(() => mutation()),
  usePreviewChunking: vi.fn(() => mutation()),
  useCompareChunking: vi.fn(() => mutation()),
}));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock("@/hooks/useEnrichments", () => ({
  usePrompts: vi.fn(() => ({ data: [], isLoading: false })),
  useCreatePrompt: vi.fn(() => mutation()),
  useLanguages: vi.fn(() => ({ data: [], isLoading: false })),
}));

function strategy(over: Partial<StrategyOut>): StrategyOut {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    label: "markdown-deep",
    slug: "markdown-deep",
    algo: "prose",
    params: {},
    parser_slug: null,
    is_system: true,
    used_by_routes: 0,
    used_by_categories: 1,
    used_by_triggers: 0,
    used_by_workspaces: 0,
    created_at: "2026-07-17T00:00:00Z",
    updated_at: "2026-07-17T00:00:00Z",
    ...over,
  };
}

function mockList(data: StrategyOut[] | undefined, isLoading = false) {
  vi.mocked(useChunkingStrategies).mockReturnValue({
    data,
    isLoading,
  } as unknown as ReturnType<typeof useChunkingStrategies>);
}

describe("ChunkingStrategiesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("affiche les stratégies avec badge système et usage", () => {
    mockList([
      strategy({}),
      strategy({
        id: "00000000-0000-0000-0000-000000000002",
        label: "Ma stratégie",
        slug: "ma-strategie",
        is_system: false,
        used_by_categories: 0,
        parser_slug: "markdown",
      }),
    ]);
    renderWithProviders(<ChunkingStrategiesPage />);

    expect(screen.getAllByText("markdown-deep").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Ma stratégie")).toBeInTheDocument();
    expect(screen.getByText("Système")).toBeInTheDocument();
    expect(screen.getByText("1 catégorie(s)")).toBeInTheDocument();
    expect(screen.getByText("Non utilisée")).toBeInTheDocument();
  });

  it("affiche l'état vide", () => {
    mockList([]);
    renderWithProviders(<ChunkingStrategiesPage />);
    expect(screen.getByText("Aucune stratégie.")).toBeInTheDocument();
  });

  it("affiche le slug en lecture seule", () => {
    mockList([strategy({})]);
    renderWithProviders(<ChunkingStrategiesPage />);
    // Le slug apparaît dans sa colonne dédiée (font-mono)
    const cells = screen.getAllByText("markdown-deep");
    expect(cells.length).toBeGreaterThanOrEqual(2); // label + slug
  });
});
